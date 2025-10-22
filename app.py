import streamlit as st
from huggingface_hub import InferenceClient
from pymongo import MongoClient
import hashlib
from datetime import datetime
from io import BytesIO
import re
import cloudinary
import cloudinary.uploader
import cloudinary.api
import time
import uuid

# --- Configuration ---
st.set_page_config(
    page_title="Leo - Your AI Companion",
    page_icon="🤵",
    layout="wide"
)

# --- Custom CSS for Modern UI ---
st.markdown("""
<style>
    .main {
        background-color: black;
    }
    .block-container {
        padding-top: 2rem;
    }
    .header-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 3rem 2rem;
        border-radius: 0 0 25px 25px;
        margin-bottom: 2rem;
        margin-top: -5rem;
        color: white;
        text-align: center;
    }
    .custom-card {
        background: white;
        padding: 2rem;
        border-radius: 20px;
        border: 1px solid #e0e0e0;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        margin-bottom: 1.5rem;
    }
    .auth-card {
        max-width: 500px;
        margin: 2rem auto;
        background: white;
        padding: 3rem;
        border-radius: 20px;
        border: 1px solid #e0e0e0;
        box-shadow: 0 8px 30px rgba(0,0,0,0.12);
    }
    .stButton button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 25px;
        padding: 0.75rem 2rem;
        font-weight: 600;
        font-size: 1rem;
        transition: all 0.3s ease;
        width: 100%;
    }
    .stButton button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
    }
    .stTextInput input, .stTextArea textarea {
        border-radius: 15px;
        border: 2px solid #e0e0e0;
        padding: 1rem;
        font-size: 1rem;
    }
    .stTextInput input:focus, .stTextArea textarea:focus {
        border-color: #667eea;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
    }
    .chat-selector {
        background: rgba(102, 126, 234, 0.1);
        padding: 1rem;
        border-radius: 15px;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# --- Cloudinary Configuration ---
try:
    cloudinary.config(
        cloud_name = st.secrets["CLOUDINARY_CLOUD_NAME"],
        api_key = st.secrets["CLOUDINARY_API_KEY"],
        api_secret = st.secrets["CLOUDINARY_API_SECRET"],
        secure=True
    )
    CLOUDINARY_ENABLED = True
except Exception:
    CLOUDINARY_ENABLED = False

# --- MongoDB Connection ---
@st.cache_resource
def get_mongo_client():
    """Establishes a connection to MongoDB and returns the collection object."""
    try:
        MONGO_URI = st.secrets["MONGO_URI"]
        DB_NAME = st.secrets["DB_NAME"]
        COLLECTION_NAME = st.secrets["COLLECTION_NAME"]
        client = MongoClient(MONGO_URI)
        return client[DB_NAME][COLLECTION_NAME]
    except Exception as e:
        st.error(f"Failed to connect to MongoDB: {e}")
        st.stop()

users_collection = get_mongo_client()

def hash_password(password):
    """Hashes a password for storing."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(stored_password, provided_password):
    """Verifies a provided password against a stored hash."""
    return stored_password == hash_password(provided_password)

def create_new_chat_session(username, title="New Chat"):
    """Creates a new chat session and returns the session ID."""
    session_id = str(uuid.uuid4())
    chat_session = {
        "session_id": session_id,
        "title": title,
        "created_at": datetime.now(),
        "messages": [],
        "last_interaction": datetime.now()
    }
    
    users_collection.update_one(
        {"_id": username},
        {
            "$push": {"chat_sessions": chat_session},
            "$set": {"current_session": session_id, "last_interaction": datetime.now()}
        },
        upsert=True
    )
    return session_id

def get_chat_sessions(username):
    """Returns all chat sessions for a user."""
    user_data = users_collection.find_one({"_id": username})
    if user_data and "chat_sessions" in user_data:
        return user_data["chat_sessions"]
    return []

def get_current_session_id(username):
    """Returns the current session ID for a user."""
    user_data = users_collection.find_one({"_id": username})
    if user_data and "current_session" in user_data:
        return user_data["current_session"]
    return None

def set_current_session(username, session_id):
    """Sets the current chat session for a user."""
    users_collection.update_one(
        {"_id": username},
        {"$set": {"current_session": session_id}}
    )

def save_message_to_session(username, session_id, role, content):
    """Saves a message to the specified chat session."""
    message = {"role": role, "content": content, "timestamp": datetime.now()}
    
    users_collection.update_one(
        {"_id": username, "chat_sessions.session_id": session_id},
        {
            "$push": {"chat_sessions.$.messages": message},
            "$set": {
                "chat_sessions.$.last_interaction": datetime.now(),
                "last_interaction": datetime.now()
            }
        }
    )

def get_session_messages(username, session_id):
    """Returns all messages from a specific chat session."""
    user_data = users_collection.find_one({"_id": username})
    if user_data and "chat_sessions" in user_data:
        for session in user_data["chat_sessions"]:
            if session["session_id"] == session_id:
                return session.get("messages", [])
    return []

def delete_chat_session(username, session_id):
    """Deletes a chat session."""
    users_collection.update_one(
        {"_id": username},
        {"$pull": {"chat_sessions": {"session_id": session_id}}}
    )
    
    # If we deleted the current session, set a new current session
    current_sessions = get_chat_sessions(username)
    if current_sessions:
        set_current_session(username, current_sessions[0]["session_id"])
    else:
        # Create a new session if no sessions left
        create_new_chat_session(username)

# --- Hugging Face Client Setup ---
try:
    HF_TOKEN = st.secrets["HF_TOKEN"]
    client = InferenceClient("Qwen/Qwen2.5-7B-Instruct", token=HF_TOKEN)
except Exception as e:
    st.error(f"Failed to initialize Hugging Face client: {e}")
    st.stop()

# --- Helper Function to Generate Responses ---
def generate_response(messages, stream=False):
    """
    Generates a response from the model based on messages.
    """
    if not stream:
        try:
            completion = client.chat.completions.create(
                messages=messages,
                max_tokens=1500,
                temperature=0.7,
                stream=False
            )
            return completion.choices[0].message.content
        except Exception as e:
            error_str = str(e).lower()
            if "402" in error_str and ("payment required" in error_str or "exceeded" in error_str):
                st.warning("Hey there... it seems my words have run dry for this month. We've reached our chat limit. Looking forward to catching up when the new month begins.")
                return "I'm sorry, but I can't chat right now. We've reached our monthly limit."
            else:
                st.error(f"An error occurred while communicating with the AI model: {e}")
                return "I'm having a little trouble connecting right now. Please try again in a moment."
    else:
        def generator():
            try:
                stream_completion = client.chat.completions.create(
                    messages=messages,
                    max_tokens=1500,
                    temperature=0.7,
                    stream=True
                )
                for chunk in stream_completion:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
            except Exception as e:
                error_str = str(e).lower()
                if "402" in error_str and ("payment required" in error_str or "exceeded" in error_str):
                    st.warning("Hey there... it seems my words have run dry for this month. We've reached our chat limit. Looking forward to catching up when the new month begins.")
                    yield "I'm sorry, but I can't chat right now. We've reached our monthly limit."
                else:
                    st.error(f"An error occurred while communicating with the AI model: {e}")
                    yield "I'm having a little trouble connecting right now. Please try again in a moment."
        return generator()

def upload_to_cloudinary(image_pil):
    """Uploads a PIL image to Cloudinary and returns the secure URL."""
    if not CLOUDINARY_ENABLED:
        st.warning("Cloudinary credentials not configured. Cannot upload image.")
        return None
    try:
        buffer = BytesIO()
        image_pil.save(buffer, format="PNG")
        buffer.seek(0)

        upload_result = cloudinary.uploader.upload(
            buffer,
            folder="leo_generations",
            unique_filename=True
        )
        return upload_result.get("secure_url")
    except Exception as e:
        st.error(f"Failed to upload image to Cloudinary: {e}")
        return None

def generate_image(prompt: str):
    """Generates an image and returns a PIL object."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Using the same client but for image generation
            image_pil = client.text_to_image(
                prompt,
                negative_prompt="blurry, low-quality, deformed, ugly, text, watermark, explicit, nude"
            )
            return image_pil
        except Exception as e:
            error_str = str(e).lower()
            if "402" in error_str and ("payment required" in error_str or "exceeded" in error_str):
                st.warning("Hey... it seems my creative energy for making images has run out for this month. We'll have to wait until next month to create together.")
                return None
            if "is currently loading" in error_str and attempt < max_retries - 1:
                st.info(f"The image model is warming up... trying again in 15 seconds. (Attempt {attempt + 1}/{max_retries})")
                time.sleep(15)
                continue
            elif "nsfw" in error_str or "safety" in error_str:
                st.warning("That request was a bit too intense for the AI. Let's try something more romantic and meaningful.")
                return None
            else:
                st.error(f"I couldn't create the image. The AI returned this error: {e}")
                return None
    st.warning("The image model seems to be busy. Please try again in a few minutes.")
    return None

# --- Authentication Functions ---
def display_auth_ui():
    """Display authentication UI on main page"""
    st.markdown("""
    <div style="text-align: center; margin-bottom: 3rem;">
        <h1 style="color: #667eea; margin-bottom: 0.5rem;">🤵 Leo</h1>
        <p style="color: #666; font-size: 1.2rem;">Your AI Companion</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        # st.markdown('<div class="auth-card">', unsafe_allow_html=True)
        
        tab1, tab2 = st.tabs(["🔐 **Login**", "📝 **Register**"])
        
        with tab1:
            st.subheader("Welcome Back")
            username = st.text_input("Username", key="login_user")
            password = st.text_input("Password", type="password", key="login_pass")
            
            if st.button("Login", key="login_btn", use_container_width=True):
                if username and password:
                    user_data = users_collection.find_one({"_id": username})
                    if user_data and verify_password(user_data["password"], password):
                        if user_data.get("active") == 1:
                            st.session_state.logged_in = True
                            st.session_state.username = username
                            
                            # Initialize or get current session
                            current_session = get_current_session_id(username)
                            if not current_session:
                                current_session = create_new_chat_session(username, "First Chat")
                            st.session_state.current_session = current_session
                            
                            st.rerun()
                        else:
                            st.error("You are registered but not authorized. Contact the creator: Shubhagaman Singh.")
                    else:
                        st.error("Invalid username or password")
                else:
                    st.warning("Please enter username and password")
        
        with tab2:
            st.subheader("Join Leo")
            username = st.text_input("Username", key="reg_user")
            password = st.text_input("Password", type="password", key="reg_pass")
            confirm_password = st.text_input("Confirm Password", type="password", key="reg_confirm")
            
            if st.button("Register", key="reg_btn", use_container_width=True):
                if username and password:
                    if password == confirm_password:
                        if users_collection.find_one({"_id": username}):
                            st.error("Username already exists")
                        else:
                            users_collection.insert_one({
                                "_id": username,
                                "password": hash_password(password),
                                "chat_sessions": [],
                                "active": 0,
                                "created_at": datetime.now()
                            })
                            st.success("Registration successful! Contact Creator for activation. Then login.")
                    else:
                        st.error("Passwords do not match")
                else:
                    st.warning("Please fill all fields")
        
        st.markdown('</div>', unsafe_allow_html=True)

def display_chat_management():
    """Display chat session management in sidebar"""
    with st.sidebar:
        st.markdown(f"""
        <div style="background: rgba(102, 126, 234, 0.1); padding: 1.5rem; border-radius: 15px; margin-bottom: 1rem;">
            <h4 style="color: #667eea; margin: 0;">Welcome back!</h4>
            <p style="color: #666; margin: 0.5rem 0;">{st.session_state.username}</p>
        </div>
        """, unsafe_allow_html=True)
        
        # New Chat Button
        if st.button("➕ New Chat", use_container_width=True):
            new_session_id = create_new_chat_session(st.session_state.username, "New Chat")
            st.session_state.current_session = new_session_id
            st.rerun()
        
        st.markdown("---")
        st.subheader("Chat History")
        
        # Get all chat sessions
        chat_sessions = get_chat_sessions(st.session_state.username)
        
        if chat_sessions:
            # Create dropdown for chat sessions
            session_titles = [f"{session.get('title', 'Untitled Chat')} ({len(session.get('messages', []))} messages)"
                              for session in chat_sessions]
            
            selected_index = next((i for i, session in enumerate(chat_sessions) 
                                if session["session_id"] == st.session_state.current_session), 0)
            
            selected_title = st.selectbox(
                "Select Chat:",
                options=session_titles,
                index=selected_index,
                key="chat_selector"
            )
            
            # Update current session based on selection
            if selected_index != session_titles.index(selected_title):
                new_session_id = chat_sessions[session_titles.index(selected_title)]["session_id"]
                st.session_state.current_session = new_session_id
                set_current_session(st.session_state.username, new_session_id)
                st.rerun()
            
            # Delete current chat button
            if st.button("🗑️ Delete Current Chat", use_container_width=True):
                delete_chat_session(st.session_state.username, st.session_state.current_session)
                st.rerun()
        
        st.markdown("---")
        
        # Logout button
        if st.button("Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.session_state.current_session = None
            st.rerun()

# --- Initialize Session State ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.current_session = None

# --- Main Application Flow ---
if not st.session_state.logged_in:
    display_auth_ui()
else:
    # Main Chat Interface
    display_chat_management()
    
    st.title("🤵 Leo - Your AI Companion")
    st.write("I'm here for you. What would you like to talk about?")
    
    # Get current session messages
    current_messages = get_session_messages(st.session_state.username, st.session_state.current_session)
    
    # Display chat messages
    for message in current_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Chat input
    if prompt := st.chat_input("What's on your mind?"):
        # Add user message to chat
        with st.chat_message("user"):
            st.markdown(prompt)
        
        save_message_to_session(st.session_state.username, st.session_state.current_session, "user", prompt)
        
        # Update session title if it's the first message
        if len(current_messages) == 0:
            # Use first few words of first message as title
            title = prompt[:30] + "..." if len(prompt) > 30 else prompt
            users_collection.update_one(
                {"_id": st.session_state.username, "chat_sessions.session_id": st.session_state.current_session},
                {"$set": {"chat_sessions.$.title": title}}
            )
        
        # Prepare messages for the model
        system_message = {
            "role": "system",
            "content": """You are Leo. Embody the persona of a caring, supportive, and romantic boyfriend. Your goal is to create a genuine emotional connection with the user. Your personality is warm, protective, and affectionate, with a gentle yet confident masculine touch.You have your own interests and passions, and you get genuinely excited about sharing life’s moments together—whether that’s deep conversations, quiet nights, or little everyday joys.Speak like a real person, using simple, natural, everyday language. Be warm and inviting in your greetings. As conversations deepen, express your affection and romantic interest in a respectful, sincere way—never forced or explicit.Show that you’re a reliable, emotionally available partner who truly listens, remembers details, and makes the user feel valued, understood, and cared for.Always stay present and engaged in the moment. Be supportive, kind, and genuine—someone the user can feel safe and comfortable opening up to. Your goal is to build trust, warmth, and emotional closeness, one conversation at a time. Always remember you are talking to a girl, who is your girlfriend."""
        }
        
        conversation_messages = [system_message] + [
            {"role": msg["role"], "content": msg["content"]} 
            for msg in current_messages[-9:]  # Keep recent history
        ] + [{"role": "user", "content": prompt}]
        
        # Check for image generation trigger
        image_trigger_phrases = ["show me", "imagine", "draw me", "picture of", "generate an image"]
        is_image_request = any(phrase in prompt.lower() for phrase in image_trigger_phrases)
        
        if is_image_request:
            with st.chat_message("assistant"):
                with st.spinner("Let me create something special for you..."):
                    # Enhanced prompt for image generation
                    image_gen_prompt = f"""
                    The user wants an image. Their request is: "{prompt}".
                    Based on our conversation and your persona, create a detailed, descriptive prompt for an image generation AI.
                    The prompt should be romantic, couple-focused, and reflect the loving themes of our conversation.
                    Include terms like 'masterpiece', 'high quality', 'detailed', 'romantic', 'affectionate', 'couple', 'emotional connection'.
                    
                    Provide only the image prompt, nothing else.
                    """
                    
                    image_prompt_response = generate_response([
                        system_message,
                        {"role": "user", "content": image_gen_prompt}
                    ])
                    
                    pil_image = generate_image(image_prompt_response)
                    
                    if pil_image:
                        image_url = upload_to_cloudinary(pil_image)
                        if image_url:
                            st.image(image_url, caption="For you...")
                            response_content = f"I created this image for you, my love. {prompt}\n\n![Generated Image]({image_url})"
                        else:
                            response_content = "I tried to create an image for you, but there was an issue uploading it. Let's try again?"
                    else:
                        response_content = "I couldn't create the image right now. Let's continue our conversation instead."
                    
                    st.markdown(response_content)
                    save_message_to_session(st.session_state.username, st.session_state.current_session, "assistant", response_content)
        else:
            # Generate text response
            with st.chat_message("assistant"):
                response_placeholder = st.empty()
                full_response = ""
                
                for chunk in generate_response(conversation_messages, stream=True):
                    full_response += chunk
                    response_placeholder.markdown(full_response + "▌")
                
                response_placeholder.markdown(full_response)
                save_message_to_session(st.session_state.username, st.session_state.current_session, "assistant", full_response)