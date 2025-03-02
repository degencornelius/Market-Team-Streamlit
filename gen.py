import streamlit as st
import json
import requests
import time
import csv
import io
from pinterest.client import PinterestSDKClient
import os

# Your existing functions (slightly modified for Streamlit)
def fetch_articles(config):
    url = f'https://newsapi.org/v2/everything?q={config["keywords"]}&apiKey={config["newsapi_key"]}'
    try:
        response = requests.get(url)
        response.raise_for_status()
        articles = response.json()['articles']
        if not articles:
            st.warning("No relevant articles found. Generating content without references.")
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

def generate_image(platform, image_prompt, model, config, filename):
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
        with open(filename, 'wb') as f:
            f.write(response.content)
        return filename
    except requests.exceptions.RequestException as e:
        st.error(f"Error generating image: {e}")
        return None

# [Include other functions: fact_check_content, upscale_image, Bannerbear functions, Pinterest upload functions]

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

    # Session state initialization
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
                    st.session_state.blog_post = blog_post
                    st.session_state.step = "approve_blog"
                    st.session_state.generated_files["blog_post.txt"] = blog_post

        if "pinterest" in config["outputs"] and st.session_state.blog_post:
            generate_pinterest_content(config)

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

    # Download generated files
    for filename, content in st.session_state.generated_files.items():
        if filename.endswith(".txt"):
            st.download_button(f"Download {filename}", content, filename, "text/plain")
        elif filename.endswith(".png"):
            st.image(content)
            st.download_button(f"Download {filename}", open(content, "rb").read(), filename, "image/png")
        elif filename.endswith(".mp4"):
            st.video(content)
            st.download_button(f"Download {filename}", open(content, "rb").read(), filename, "video/mp4")
        elif filename.endswith(".csv"):
            st.download_button(f"Download {filename}", content, filename, "text/csv")

def generate_blog_post(config, reference_links):
    prompt = f"Write a {config['article_length']} word {config['intent']} blog post about {config['keywords']}..."
    # [Add your full prompt logic here]
    return generate_content(prompt, config["text_model"], config)

def revise_blog_post(blog_post, feedback, config, reference_links):
    prompt = f"Revise the following blog post based on this feedback: {feedback}\n\nOriginal content: {blog_post}..."
    # [Add your full revision prompt logic here]
    return generate_content(prompt, config["text_model"], config)

def generate_pinterest_content(config):
    for i in range(config["post_ratio"]):
        with st.spinner(f"Generating Pinterest post {i+1}..."):
            # [Add your Pinterest generation logic here, adapted to use st.session_state.pin_data_list]
            st.session_state.pin_data_list.append({"Title": f"Pin {i+1}", "Media URL": "example.com"})
            # Generate image, video, etc., and store in st.session_state.generated_files

if __name__ == "__main__":
    main()