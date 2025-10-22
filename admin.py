import streamlit as st # type: ignore

# --- Page Configuration ---
if "page_config_set" not in st.session_state:
    st.set_page_config(
        page_title="Leo Admin Panel",
        page_icon="🔑",
        layout="wide"
    )
    st.session_state.page_config_set = True

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
        padding: 2.5rem 2rem;
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
    .user-card {
        background: white;
        padding: 1.5rem;
        border-radius: 15px;
        border: 1px solid #e0e0e0;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        margin-bottom: 1rem;
        transition: all 0.3s ease;
    }
    .user-card:hover {
        box-shadow: 0 4px 20px rgba(102, 126, 234, 0.15);
        transform: translateY(-2px);
    }
    .status-active {
        color: #10b981;
        font-weight: 600;
    }
    .status-inactive {
        color: #ef4444;
        font-weight: 600;
    }
    .stats-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 15px;
        text-align: center;
    }
    /* Hide default Streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

from pymongo import MongoClient # type: ignore
import hashlib
from datetime import datetime
import json

# --- MongoDB Connection ---
@st.cache_resource
def get_db():
    """Establishes a connection to MongoDB and returns the database object."""
    try:
        MONGO_URI = st.secrets["MONGO_URI"]
        DB_NAME = st.secrets["DB_NAME"]
        client = MongoClient(MONGO_URI)
        return client[DB_NAME]
    except Exception as e:
        st.error(f"Failed to connect to MongoDB: {e}")
        st.stop()

def hash_password(password):
    """Hashes a password for storing."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(stored_password, provided_password):
    """Verifies a provided password against a stored hash."""
    return stored_password == hash_password(provided_password)

# Initialize database connection
db = get_db()
users_collection = db[st.secrets["COLLECTION_NAME"]]
admin_collection = db["admin"]

# --- UI Components ---
def display_modern_header():
    """Display modern header with gradient"""
    st.markdown("""
    <div class="header-container">
        <h1 style="margin:0; font-size: 2.5rem; font-weight: 700;">🔑 Leo Admin Panel</h1>
        <p style="margin:0; font-size: 1.2rem; opacity: 0.9;">User Management Dashboard</p>
    </div>
    """, unsafe_allow_html=True)

def display_stats():
    """Display statistics cards"""
    total_users = users_collection.count_documents({})
    active_users = users_collection.count_documents({"active": 1})
    inactive_users = total_users - active_users
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f"""
        <div class="stats-card">
            <h3 style="margin:0; font-size: 2rem;">{total_users}</h3>
            <p style="margin:0; opacity: 0.9;">Total Users</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="stats-card">
            <h3 style="margin:0; font-size: 2rem;">{active_users}</h3>
            <p style="margin:0; opacity: 0.9;">Active Users</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="stats-card">
            <h3 style="margin:0; font-size: 2rem;">{inactive_users}</h3>
            <p style="margin:0; opacity: 0.9;">Inactive Users</p>
        </div>
        """, unsafe_allow_html=True)

def display_user_card(user):
    """Display individual user card with actions"""
    username = user["_id"]
    is_active = user.get("active", 0) == 1
    created_at = user.get("created_at", datetime.now())
    chat_sessions = user.get("chat_sessions", [])
    total_chats = len(chat_sessions)
    
    # Calculate total messages
    total_messages = 0
    for session in chat_sessions:
        total_messages += len(session.get("messages", []))
    
    with st.container():
        st.markdown('<div class="user-card">', unsafe_allow_html=True)
        
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        
        with col1:
            st.subheader(username)
            st.caption(f"Registered: {created_at.strftime('%Y-%m-%d %H:%M')}")
            st.write(f"**Chats:** {total_chats} | **Messages:** {total_messages}")
        
        with col2:
            status_color = "🟢" if is_active else "🔴"
            status_text = "Active" if is_active else "Inactive"
            st.markdown(f"**Status:** {status_color} {status_text}")
        
        with col3:
            if is_active:
                if st.button("🚫 Deactivate", key=f"deactivate_{username}", use_container_width=True):
                    users_collection.update_one({"_id": username}, {"$set": {"active": 0}})
                    st.success(f"User '{username}' deactivated")
                    st.rerun()
            else:
                if st.button("✅ Activate", key=f"activate_{username}", use_container_width=True):
                    users_collection.update_one({"_id": username}, {"$set": {"active": 1}})
                    st.success(f"User '{username}' activated")
                    st.rerun()
        
        with col4:
            if st.button("🗑️ Delete", key=f"delete_{username}", type="secondary", use_container_width=True):
                if "confirm_delete" not in st.session_state or st.session_state.confirm_delete != username:
                    st.session_state.confirm_delete = username
                    st.warning(f"Click delete again to confirm deletion of user '{username}'")
                    st.rerun()
                else:
                    users_collection.delete_one({"_id": username})
                    st.error(f"User '{username}' permanently deleted")
                    if "confirm_delete" in st.session_state:
                        del st.session_state.confirm_delete
                    st.rerun()
        
        # Chat sessions expander
        with st.expander("View Chat Sessions"):
            if not chat_sessions:
                st.info("No chat sessions found")
            else:
                for i, session in enumerate(chat_sessions):
                    session_title = session.get("title", f"Chat {i+1}")
                    messages = session.get("messages", [])
                    last_interaction = session.get("last_interaction", created_at)
                    
                    st.write(f"**{session_title}** ({len(messages)} messages)")
                    st.caption(f"Last active: {last_interaction.strftime('%Y-%m-%d %H:%M')}")
                    
                    # Show recent messages
                    if messages:
                        recent_messages = messages[-3:]  # Show last 3 messages
                        for msg in recent_messages:
                            role_icon = "👤" if msg["role"] == "user" else "🤖"
                            st.text_area(
                                f"{role_icon} {msg['role'].title()}",
                                msg["content"],
                                height=60,
                                key=f"msg_{username}_{i}_{msg['timestamp']}",
                                disabled=True
                            )
        
        st.markdown('</div>', unsafe_allow_html=True)

# --- Admin Authentication ---
def check_admin_login():
    """Check if admin is logged in"""
    if st.session_state.get("admin_logged_in"):
        return True
    return False

# Initialize session state
if 'admin_logged_in' not in st.session_state:
    st.session_state.admin_logged_in = False
if 'admin_username' not in st.session_state:
    st.session_state.admin_username = ""

# Main application flow
if not check_admin_login():
    display_modern_header()
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown('<div class="auth-card">', unsafe_allow_html=True)
        
        st.markdown("""
        <div style="text-align: center; margin-bottom: 2rem;">
            <h2 style="color: #667eea; margin-bottom: 0.5rem;">🔑 Admin Access</h2>
            <p style="color: #666;">Leo User Management System</p>
        </div>
        """, unsafe_allow_html=True)
        
        admin_username = st.text_input("Admin Username", key="admin_user")
        admin_password = st.text_input("Admin Password", type="password", key="admin_pass")
        
        if st.button("Login", key="admin_login_btn", use_container_width=True):
            if admin_username and admin_password:
                admin_user_data = admin_collection.find_one({"_id": admin_username})
                if admin_user_data and verify_password(admin_user_data.get("password", ""), admin_password):
                    st.session_state.admin_logged_in = True
                    st.session_state.admin_username = admin_username
                    st.rerun()
                else:
                    st.error("Invalid admin credentials")
            else:
                st.warning("Please enter both username and password")
        
        st.markdown('</div>', unsafe_allow_html=True)

else:
    # Main Admin Panel - User is logged in
    display_modern_header()
    
    # Sidebar
    with st.sidebar:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    padding: 1.5rem; border-radius: 15px; margin-bottom: 1rem; color: white;">
            <h4 style="margin:0;">Welcome, Admin!</h4>
            <p style="margin:0.5rem 0; opacity: 0.9;">{st.session_state.admin_username}</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        st.subheader("Quick Actions")
        
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.rerun()
            
        if st.button("📊 View Statistics", use_container_width=True):
            st.session_state.show_stats = True
            
        if st.button("👥 Manage Users", use_container_width=True):
            st.session_state.show_stats = False
            
        st.markdown("---")
        
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.admin_logged_in = False
            st.session_state.admin_username = ""
            st.rerun()
    
    # Main content area
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("User Management")
    
    with col2:
        search_term = st.text_input("Search users", placeholder="Enter username...")
    
    # Display statistics or user list
    if st.session_state.get("show_stats", True):
        display_stats()
    
    # Fetch and display users
    try:
        query = {}
        if search_term:
            query["_id"] = {"$regex": search_term, "$options": "i"}
        
        all_users = list(users_collection.find(query, {"password": 0}))
        
        if not all_users:
            st.info("No users found in the database.")
        else:
            # Sort users: active first, then by username
            all_users.sort(key=lambda x: (-x.get('active', 0), x['_id']))
            
            for user in all_users:
                display_user_card(user)
                
    except Exception as e:
        st.error(f"Failed to fetch users: {e}")

# Auto-refresh every 5 seconds to show real-time updates
st_autorefresh = st.empty()
if st.session_state.get("admin_logged_in"):
    st_autorefresh.markdown("""
    <script>
    setTimeout(function() {
        window.location.reload();
    }, 5000);
    </script>
    """, unsafe_allow_html=True)