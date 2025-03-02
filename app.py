import streamlit as st
import json
import requests
import time
import csv
import io
from pinterest.client import PinterestSDKClient
import os

# Functions (adapted from your original script)
def fetch_articles(config):
    url = f'https://newsapi.org/v2/everything?q={config["keywords"]}&apiKey={config["newsapi_key"]}'
    try:
        response = requests.get(url)
        response.raise_for_status()
        articles = response.json()['articles']
        if not articles:
            st.warning("No relevant articles found.")
            return []
        required_keywords = ["mindfulness", "meditation", "stress", "mental"]
        filtered_articles = [
            (article['title'], article['description'], article['url'])
            for article in articles
            if any(keyword.lower() in article['title'].lower() or keyword.lower() in article['description'].lower() for keyword in required_keywords)
        ]
        return filtered_articles[:5] if filtered_articles else []
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching articles: {e}")
        return []

def generate_content(prompt, model, config, system_prompt="You are an expert blog writer."):
    headers = {"Authorization": f"Bearer {config['veniceai_key']}", "Content-Type": "application/json"}
    request_data = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]
    }
    try:
        response = requests.post("https://api.venice.ai/api/v1/chat/completions", headers=headers, json=request_data)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except requests.exceptions.RequestException as e:
        st.error(f"Error generating content: {e}")
        return None

def generate_image(platform, image_prompt, model, config):
    width = config["platform_settings"][platform]["image_width"]
    height = config["platform_settings"][platform]["image_height"]
    headers = {"Authorization": f"Bearer {config['veniceai_key']}", "Content-Type": "application/json"}
    request_data = {
        "model": model,
        "prompt": image_prompt,
        "height": height,
        "width": width,
        "return_binary": True,
        "safe_mode": True,
        "hide_watermark": True
    }
    try:
        response = requests.post("https://api.venice.ai/api/v1/image/generate", headers=headers, json=request_data)
        response.raise_for_status()
        return response.content  # Return bytes instead of saving to file
    except requests.exceptions.RequestException as e:
        st.error(f"Error generating image: {e}")
        return None

def fact_check_content(content, config, references=None):
    prompt = "Verify the accuracy of the following content...\n\n" + content
    if references:
        prompt += f"\n\nReferences: {', '.join(references)}"
    response = generate_content(prompt, config["text_model"], config, "You are an expert fact-checker.")
    if response:
        try:
            confidence = int(response.split("Confidence:")[1].split()[0])
            explanation = response.split(" - ")[1]
            return confidence >= 60, confidence, explanation
        except:
            return False, 50, "Failed to parse fact-check response."
    return False, 0, "Fact-checking failed."

def upscale_image(image_bytes, scale_factor, config):
    url = "https://api.venice.ai/api/v1/image/upscale"
    headers = {"Authorization": f"Bearer {config['veniceai_key']}"}
    files = {"image": ("image.png", image_bytes, "image/png")}
    data = {"scale": scale_factor}
    try:
        response = requests.post(url, headers=headers, files=files, data=data)
        response.raise_for_status()
        return response.content
    except requests.exceptions.RequestException as e:
        st.error(f"Error upscaling image: {e}")
        return None

def upload_image_to_bannerbear(image_bytes, config):
    url = "https://api.bannerbear.com/v2/images"
    headers = {"Authorization": f"Bearer {config['bannerbear_key']}"}
    files = {"image": ("image.png", image_bytes, "image/png")}
    try:
        response = requests.post(url, headers=headers, files=files)
        response.raise_for_status()
        return response.json()["uid"]
    except requests.exceptions.RequestException as e:
        st.error(f"Error uploading to Bannerbear: {e}")
        return None

def create_video_rendering(template_id, modifications, config):
    url = "https://api.bannerbear.com/v2/renders"
    headers = {"Authorization": f"Bearer {config['bannerbear_key']}", "Content-Type": "application/json"}
    data = {"template": template_id, "modifications": modifications}
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()["uid"]
    except requests.exceptions.RequestException as e:
        st.error(f"Error creating video render: {e}")
        return None

def wait_for_video(uid, config):
    url = f"https://api.bannerbear.com/v2/renders/{uid}"
    headers = {"Authorization": f"Bearer {config['bannerbear_key']}"}
    start_time = time.time()
    while time.time() - start_time < 600:  # 10 min timeout
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            status = response.json()
            if status["status"] == "completed":
                return status["video_url"]
            elif status["status"] == "failed":
                st.error("Video rendering failed.")
                return None
        time.sleep(10)
    st.error("Video rendering timed out.")
    return None

def download_video(video_url):
    try:
        response = requests.get(video_url)
        response.raise_for_status()
        return response.content
    except requests.exceptions.RequestException as e:
        st.error(f"Error downloading video: {e}")
        return None

def upload_video_to_pinterest(video_bytes, title, description, board_id, config):
    url = "https://api-sandbox.pinterest.com/v5/pins"
    headers = {"Authorization": f"Bearer {config['pinterest_access_token']}"}
    files = {"media": ("video.mp4", video_bytes, "video/mp4")}
    data = {
        "board_id": board_id,
        "title": title,
        "description": description,
        "media_type": "video",
        "link": config.get("affiliate_link", "https://example.com")
    }
    try:
        response = requests.post(url, headers=headers, files=files, data=data)
        response.raise_for_status()
        pin_id = response.json()["id"]
        return f"https://www.pinterest.com/pin/{pin_id}/"
    except requests.exceptions.RequestException as e:
        st.error(f"Error uploading to Pinterest: {e}")
        return None

# Main app
def main():
    st.title("Content Generation Dashboard")
    st.write("Generate blog posts and Pinterest content with AI.")

    # Config input
    st.sidebar.header("Configuration")
    config_option = st.sidebar.radio("Load config via:", ["Form", "Upload JSON"])
    if config_option == "Form":
        config = {
            "newsapi_key": st.sidebar.text_input("NewsAPI Key"),
            "veniceai_key": st.sidebar.text_input("VeniceAI Key"),
            "text_model": st.sidebar.selectbox("Text Model", ["llama-3.3-70b", "other_model"]),
            "image_model": st.sidebar.selectbox("Image Model", ["flux-dev", "other_model"]),
            "keywords": st.sidebar.text_input("Keywords", "mindfulness bundle, stress relief"),
            "intent": st.sidebar.selectbox("Intent", ["informative", "educational", "entertaining", "inspirational", "analytical", "transactional"]),
            "article_length": st.sidebar.number_input("Article Length", min_value=100, value=500),
            "pinterest_access_token": st.sidebar.text_input("Pinterest Access Token"),
            "bannerbear_key": st.sidebar.text_input("Bannerbear Key"),
            "bannerbear_template_id": st.sidebar.text_input("Bannerbear Template ID"),
            "outputs": st.sidebar.multiselect("Outputs", ["blog", "pinterest"], default=["pinterest"]),
            "post_ratio": st.sidebar.number_input("Pinterest Posts", min_value=1, value=3),
            "target_audience": st.sidebar.text_input("Target Audience", "busy professionals"),
            "call_to_action": st.sidebar.text_input("Call to Action", "Get the Mindfulness Bundle Now!"),
            "affiliate_link": st.sidebar.text_input("Affiliate Link", "https://payhip.com/b/tnVQN"),
            "seo_keywords": st.sidebar.text_area("SEO Keywords (comma-separated)", "mindfulness bundle, stress relief").split(", "),
            "content_format": st.sidebar.text_input("Content Format", "listicle"),
            "tone_and_style": st.sidebar.text_input("Tone and Style", "uplifting and conversational"),
            "image_style": st.sidebar.text_input("Image Style", "realistic"),
            "platform_settings": {"blog": {"image_width": 800, "image_height": 600}, "pinterest": {"image_width": 864, "image_height": 1280}}
        }
    else:
        uploaded_file = st.sidebar.file_uploader("Upload config.json", type="json")
        if uploaded_file:
            config = json.load(uploaded_file)
            config["platform_settings"] = {"blog": {"image_width": 800, "image_height": 600}, "pinterest": {"image_width": 864, "image_height": 1280}}
        else:
            st.sidebar.warning("Please upload a config.json file.")
            return

    # Validate config
    required_fields = ['newsapi_key', 'veniceai_key', 'text_model', 'image_model', 'keywords', 'intent', 'article_length', 'pinterest_access_token', 'bannerbear_key', 'bannerbear_template_id']
    if not all(config.get(field) for field in required_fields):
        st.error("Missing required fields in config.")
        return

    # Session state
    if "step" not in st.session_state:
        st.session_state.step = "start"
        st.session_state.blog_post = None
        st.session_state.pin_data_list = []
        st.session_state.generated_files = {}

    # Main workflow
    if st.button("Start Generation"):
        with st.spinner("Fetching articles..."):
            article_data = fetch_articles(config)
            reference_links = [url for _, _, url in article_data] if article_data else []

        if "blog" in config["outputs"] or "pinterest" in config["outputs"]:
            with st.spinner("Generating blog post..."):
                blog_post = generate_blog_post(config, reference_links)
                if blog_post:
                    passed, score, explanation = fact_check_content(blog_post, config, reference_links)
                    if passed:
                        st.session_state.blog_post = blog_post
                        st.session_state.generated_files["blog_post.txt"] = blog_post
                        st.session_state.step = "approve_blog"
                    else:
                        st.warning(f"Fact-check failed: {score}% - {explanation}")

    # Approval workflow
    if st.session_state.step == "approve_blog" and st.session_state.blog_post:
        st.subheader("Review Blog Post")
        st.write(st.session_state.blog_post)
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Approve Blog"):
                st.session_state.step = "generate_images"
        with col2:
            if st.button("Reject Blog"):
                st.session_state.step = "start"
                st.session_state.blog_post = None
        with col3:
            feedback = st.text_input("Feedback for Revision")
            if st.button("Revise Blog") and feedback:
                with st.spinner("Revising blog post..."):
                    st.session_state.blog_post = revise_blog_post(st.session_state.blog_post, feedback, config, reference_links)
                    st.session_state.generated_files["blog_post.txt"] = st.session_state.blog_post
                st.rerun()

    # Image and Pinterest generation
    if st.session_state.step == "generate_images":
        if "blog" in config["outputs"]:
            with st.spinner("Generating blog image..."):
                blog_image_prompt = generate_content(
                    f"Create a vivid image description for a blog post about {config['keywords']}...",
                    config["text_model"], config, "You are a creative visual designer."
                )
                blog_image = generate_image("blog", blog_image_prompt, config["image_model"], config)
                if blog_image:
                    upscaled_image = upscale_image(blog_image, 2, config)
                    if upscaled_image:
                        st.session_state.generated_files["blog_image_upscaled.png"] = upscaled_image

        if "pinterest" in config["outputs"] and st.session_state.blog_post:
            generate_pinterest_content(config)

        st.session_state.step = "done"

    # Display and download
    if st.session_state.step == "done":
        st.success("Content generation complete!")
        for filename, content in st.session_state.generated_files.items():
            if filename.endswith(".txt"):
                st.download_button(f"Download {filename}", content, filename, "text/plain")
            elif filename.endswith(".png"):
                st.image(content, caption=filename)
                st.download_button(f"Download {filename}", content, filename, "image/png")
            elif filename.endswith(".mp4"):
                st.video(content)
                st.download_button(f"Download {filename}", content, filename, "video/mp4")
        if st.session_state.pin_data_list:
            csv_buffer = io.StringIO()
            writer = csv.DictWriter(csv_buffer, fieldnames=["Title", "Media URL", "Pinterest board", "Thumbnail", "Description", "Link", "Publish date", "Keywords"])
            writer.writeheader()
            writer.writerows(st.session_state.pin_data_list)
            st.download_button("Download Pinterest CSV", csv_buffer.getvalue(), f"pinterest_bulk_upload_{time.strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")

def generate_blog_post(config, reference_links):
    prompt = (f"Write a {config['article_length']} word {config['intent']} blog post about {config['keywords']} "
              f"for {config['target_audience']} in a {config['tone_and_style']} tone using a {config['content_format']} format. "
              f"Incorporate SEO keywords: {', '.join(config['seo_keywords'])}. "
              f"References: {', '.join(reference_links) if reference_links else 'Use general knowledge.'} "
              f"Include call to action: '{config['call_to_action']}' with link <a href='{config['affiliate_link']}'>Obtain Mindfulness Bundle</a>.")
    return generate_content(prompt, config["text_model"], config)

def revise_blog_post(blog_post, feedback, config, reference_links):
    prompt = (f"Revise this blog post based on feedback: {feedback}\n\nOriginal: {blog_post}\n\n"
              f"Maintain {config['article_length']} words, {config['intent']} intent, {config['tone_and_style']} tone, "
              f"and {config['content_format']} format for {config['target_audience']}. "
              f"References: {', '.join(reference_links) if reference_links else 'Use general knowledge.'}")
    return generate_content(prompt, config["text_model"], config)

def generate_pinterest_content(config):
    for i in range(config["post_ratio"]):
        with st.spinner(f"Generating Pinterest post {i+1}..."):
            pinterest_prompt = (f"Create a Pinterest post for '{config['keywords']}', aspect {i+1}. "
                                f"Include title, description, and 5-10 hashtags.\nBlog post: {st.session_state.blog_post[:200]}")
            pinterest_post = generate_content(pinterest_prompt, config["text_model"], config, "You are a social media manager.")
            title = pinterest_post.split("Title:")[1].split("\n")[0].strip()
            description = pinterest_post.split("Description:")[1].split("\n")[0].strip()
            hashtags = pinterest_post.split("Hashtags:")[1].split()

            image_prompt = f"Create a vivid image for '{title}' about {config['keywords']}..."
            image_bytes = generate_image("pinterest", image_prompt, config["image_model"], config)
            if image_bytes:
                upscaled_image = upscale_image(image_bytes, 2, config)
                if upscaled_image:
                    image_uid = upload_image_to_bannerbear(upscaled_image, config)
                    if image_uid:
                        modifications = [
                            {"name": "image_layer", "image_uid": image_uid},
                            {"name": "title_text", "text": title},
                            {"name": "description_text", "text": description[:100]}
                        ]
                        render_uid = create_video_rendering(config["bannerbear_template_id"], modifications, config)
                        if render_uid:
                            video_url = wait_for_video(render_uid, config)
                            if video_url:
                                video_bytes = download_video(video_url)
                                if video_bytes:
                                    pin_url = upload_video_to_pinterest(video_bytes, title, f"{description} {' '.join(hashtags)}", "your_board_id", config)
                                    if pin_url:
                                        st.session_state.pin_data_list.append({
                                            "Title": title,
                                            "Media URL": pin_url,
                                            "Pinterest board": "Mindfulness Tips",
                                            "Thumbnail": "",
                                            "Description": description,
                                            "Link": config["affiliate_link"],
                                            "Publish date": "",
                                            "Keywords": ", ".join(config["seo_keywords"])
                                        })
                                        st.session_state.generated_files[f"pinterest_video_{i+1}.mp4"] = video_bytes

if __name__ == "__main__":
    main()