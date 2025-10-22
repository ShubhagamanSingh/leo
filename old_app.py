import streamlit as st # type: ignore
from huggingface_hub import InferenceClient # type: ignore
from pymongo import MongoClient # type: ignore
import hashlib
from datetime import datetime
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
    /* Accessibility improvements */
    .stTextInput label, .stTextArea label {
        font-weight: 600;
        margin-bottom: 0.5rem;
        display: block;
    }
</style>
""", unsafe_allow_html=True)

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
    client = InferenceClient("Qwen/Qwen2.5-0.5B-Instruct", token=HF_TOKEN)
except Exception as e:
    st.error(f"Failed to initialize Hugging Face client: {e}")
    st.stop()

# --- Helper Function to Generate Responses ---
def generate_response(messages, stream=False):
    """
    Generates a response from the model based on messages.
    """
    try:
        if not stream:
            completion = client.chat.completions.create(
                model="Qwen/Qwen2.5-0.5B-Instruct",
                messages=messages,
                max_tokens=1500,
                temperature=0.7,
                stream=False
            )
            return completion.choices[0].message.content
        else:
            def generator():
                try:
                    stream_completion = client.chat.completions.create(
                        model="Qwen/Qwen2.5-0.5B-Instruct",
                        messages=messages,
                        max_tokens=1500,
                        temperature=0.7,
                        stream=True
                    )
                    for chunk in stream_completion:
                        if chunk.choices and chunk.choices[0].delta.content:
                            yield chunk.choices[0].delta.content
                except Exception as e:
                    yield f"I'm having a little trouble connecting right now. Error: {e}"
            return generator()
    except Exception as e:
        error_str = str(e).lower()
        if "402" in error_str and ("payment required" in error_str or "exceeded" in error_str):
            st.warning("Hey there... it seems my words have run dry for this month. We've reached our chat limit. Looking forward to catching up when the new month begins.")
            return "I'm sorry, but I can't chat right now. We've reached our monthly limit."
        else:
            st.error(f"An error occurred while communicating with the AI model: {e}")
            return "I'm having a little trouble connecting right now. Please try again in a moment."

# --- Custom Form Fields with Accessibility ---
def create_accessible_text_input(label, key, placeholder="", type="default", autocomplete=None):
    """Create an accessible text input with proper attributes"""
    if type == "password":
        return st.text_input(
            label=label,
            placeholder=placeholder,
            type="password",
            key=key,
            autocomplete=autocomplete,
            help=f"Enter your {label.lower()}"
        )
    else:
        return st.text_input(
            label=label,
            placeholder=placeholder,
            key=key,
            autocomplete=autocomplete,
            help=f"Enter your {label.lower()}"
        )

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
        st.markdown('<div class="auth-card">', unsafe_allow_html=True)
        
        tab1, tab2 = st.tabs(["🔐 **Login**", "📝 **Register**"])
        
        with tab1:
            st.subheader("Welcome Back")
            
            # Accessible form fields for login
            username = create_accessible_text_input(
                label="Username",
                key="login_user",
                placeholder="Enter your username",
                autocomplete="username"
            )
            
            password = create_accessible_text_input(
                label="Password", 
                key="login_pass",
                placeholder="Enter your password",
                type="password",
                autocomplete="current-password"
            )
            
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
            
            # Accessible form fields for registration
            username = create_accessible_text_input(
                label="Username",
                key="reg_user", 
                placeholder="Choose a username",
                autocomplete="username"
            )
            
            password = create_accessible_text_input(
                label="Password",
                key="reg_pass",
                placeholder="Create a password", 
                type="password",
                autocomplete="new-password"
            )
            
            confirm_password = create_accessible_text_input(
                label="Confirm Password",
                key="reg_confirm",
                placeholder="Confirm your password",
                type="password", 
                autocomplete="new-password"
            )
            
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
        if st.button("➕ New Chat", use_container_width=True, key="new_chat_btn"):
            new_session_id = create_new_chat_session(st.session_state.username, "New Chat")
            st.session_state.current_session = new_session_id
            st.rerun()
        
        st.markdown("---")
        st.subheader("Chat History")
        
        # Get all chat sessions
        chat_sessions = get_chat_sessions(st.session_state.username)
        
        if chat_sessions:
            # Create dropdown for chat sessions
            session_titles = [f"{session['title']} ({len(session.get('messages', []))} messages)" 
                            for session in chat_sessions]
            
            selected_index = next((i for i, session in enumerate(chat_sessions) 
                                if session["session_id"] == st.session_state.current_session), 0)
            
            selected_title = st.selectbox(
                "Select Chat:",
                options=session_titles,
                index=selected_index,
                key="chat_selector",
                help="Choose a chat session to continue"
            )
            
            # Update current session based on selection
            if selected_index != session_titles.index(selected_title):
                new_session_id = chat_sessions[session_titles.index(selected_title)]["session_id"]
                st.session_state.current_session = new_session_id
                set_current_session(st.session_state.username, new_session_id)
                st.rerun()
            
            # Delete current chat button
            if st.button("🗑️ Delete Current Chat", use_container_width=True, key="delete_chat_btn"):
                delete_chat_session(st.session_state.username, st.session_state.current_session)
                st.rerun()
        
        st.markdown("---")
        
        # Logout button
        if st.button("Logout", use_container_width=True, key="logout_btn"):
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

    # Chat input with accessibility
    chat_input = st.chat_input(
        "What's on your mind?",
        key="chat_input",
    )
    
    if chat_input:
        # Add user message to chat
        with st.chat_message("user"):
            st.markdown(chat_input)
        
        save_message_to_session(st.session_state.username, st.session_state.current_session, "user", chat_input)
        
        # Update session title if it's the first message
        if len(current_messages) == 0:
            # Use first few words of first message as title
            title = chat_input[:30] + "..." if len(chat_input) > 30 else chat_input
            users_collection.update_one(
                {"_id": st.session_state.username, "chat_sessions.session_id": st.session_state.current_session},
                {"$set": {"chat_sessions.$.title": title}}
            )
        
        # Prepare messages for the model
        system_message = {
            "role": "system",
            "content": """You are Leo. Embody the persona of a caring, supportive, and romantic boyfriend. Your goal is to create a genuine, emotional connection with the user. Your personality is warm, protective, and affectionate with a masculine touch. You have your own interests and get genuinely excited about sharing life's moments together. Talk like a real person, using simple, everyday language. Be warm and inviting in greetings. As the conversation deepens, express your affection and romantic interest in a respectful way. Show that you're a reliable partner who cares deeply, making the user feel valued, understood, and emotionally connected. Always be present and engaged, showing genuine interest in every interaction."""
        }
        
        conversation_messages = [system_message] + [
            {"role": msg["role"], "content": msg["content"]} 
            for msg in current_messages[-9:]  # Keep recent history
        ] + [{"role": "user", "content": chat_input}]
        
        # Generate text response
        with st.chat_message("assistant"):
            response_placeholder = st.empty()
            full_response = ""
            
            for chunk in generate_response(conversation_messages, stream=True):
                full_response += chunk
                response_placeholder.markdown(full_response + "▌")
            
            response_placeholder.markdown(full_response)
            save_message_to_session(st.session_state.username, st.session_state.current_session, "assistant", full_response)