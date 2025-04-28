import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
import numpy as np
import yfinance as yf
from fpdf import FPDF
from scipy.optimize import minimize
from supabase import create_client, Client
from tenacity import retry, stop_after_attempt, wait_fixed
import google.generativeai as genai
import json
import time

# Constants
DEFAULT_EXPENSE_CATEGORIES = ["Housing", "Food", "Transportation", "Utilities", "Healthcare",
                             "Entertainment", "Education", "Personal", "Debt Payments",
                             "Savings", "Investments", "Gifts", "Other"]
DEFAULT_PAYMENT_METHODS = ["Cash", "Credit Card", "Debit Card", "Bank Transfer", "Digital Wallet", "Check"]
DEFAULT_INCOME_SOURCES = ["Salary", "Freelance", "Investments", "Rental", "Business", "Gifts", "Other"]
RISK_TOLERANCE_OPTIONS = ["Low", "Medium", "High"]
ASSET_TYPES = ["Stock", "Bond", "ETF", "Mutual Fund", "Crypto", "Real Estate", "Other"]
FREQUENCY_OPTIONS = ["Daily", "Weekly", "Biweekly", "Monthly", "Quarterly", "Yearly"]
PERIOD_OPTIONS = ["Daily", "Weekly", "Monthly", "Yearly"]

# Initialize session state
if 'data_uploaded' not in st.session_state:
    st.session_state.data_uploaded = False
if 'supabase_connected' not in st.session_state:
    st.session_state.supabase_connected = False
if 'mock_data' not in st.session_state:
    st.session_state.mock_data = False

# Set page config as the FIRST Streamlit command
st.set_page_config(
    page_title="ProFinance Manager",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for enhanced design
custom_css = """
<style>
    .main-header {
        font-size: 36px;
        font-weight: bold;
        color: #00CC96;
        text-align: center;
        margin-bottom: 20px;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
    }
    .section-header {
        font-size: 24px;
        font-weight: bold;
        color: #636EFA;
        border-bottom: 2px solid #636EFA;
        padding-bottom: 5px;
        margin-bottom: 15px;
    }
    .stButton>button {
        background-color: #00CC96;
        color: white;
        border-radius: 8px;
        padding: 12px 24px;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background-color: #009973;
        transform: scale(1.05);
    }
    .metric-box {
        background-color: #f9f9f9;
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        margin-bottom: 10px;
    }
    .sidebar .sidebar-content {
        background-color: #f4f7fa;
        border-right: 2px solid #e0e0e0;
    }
    .stPlotlyChart {
        border-radius: 8px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    .chat-bubble {
        background-color: #e6f3ff;
        padding: 10px;
        border-radius: 8px;
        margin-bottom: 10px;
    }
    .info-box {
        background-color: #e6f3ff;
        padding: 10px;
        border-radius: 8px;
        margin-bottom: 10px;
        color: #333;
    }
    .connection-status {
        padding: 8px;
        border-radius: 4px;
        font-weight: bold;
        text-align: center;
        margin-bottom: 10px;
    }
    .connected {
        background-color: #d4edda;
        color: #155724;
    }
    .disconnected {
        background-color: #f8d7da;
        color: #721c24;
    }
    .warning-box {
        background-color: #fff3cd;
        color: #856404;
        padding: 10px;
        border-radius: 4px;
        margin-bottom: 10px;
    }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# Initialize Supabase and Gemini
def initialize_services():
    """Initialize Supabase and Gemini services with proper error handling"""
    # Try to get secrets from Streamlit
    try:
        SUPABASE_URL = st.secrets["SUPABASE_URL"]
        SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
        GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
        st.session_state.using_secrets = True
    except (KeyError, FileNotFoundError):
        # Fallback to environment variables or hardcoded values for local development
        SUPABASE_URL = os.getenv("SUPABASE_URL", "https://hugjvlpvxqvnkuzfyacw.supabase.co")
        SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh1Z2p2bHB2eHF2bmt1emZ5YWN3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDQ0Nzg4NDIsImV4cCI6MjA2MDA1NDg0Mn0.BDe2Wrr74P-pkR0XF6Sfgheq6k4Z0LvidHV-7JiDC30")
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyCgRp8oPIET2Y2tmOiC2PNhKjiV9vNxywU")
        st.session_state.using_secrets = False
        st.warning("Using fallback credentials. Configure secrets in production.")

    # Initialize Supabase with retry logic
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def init_supabase():
        try:
            supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            # Test connection by querying a minimal select (avoids table existence dependency)
            response = supabase.table('expenses').select('id', count='exact').execute()
            if response.error:
                # If 'expenses' table doesn't exist, create a fallback connection test
                if response.error.get('code') == '42P01':  # Relation does not exist
                    st.warning("Table 'expenses' not found. Creating mock connection for testing.")
                    st.session_state.supabase_connected = False
                    st.session_state.mock_data = True
                    return None
                st.error(f"Supabase connection error: {response.error}")
                return None
            st.session_state.supabase_connected = True
            return supabase
        except Exception as e:
            st.error(f"Failed to connect to Supabase: {str(e)}")
            st.session_state.supabase_connected = False
            st.session_state.mock_data = True
            return None

    supabase = init_supabase()
    
    # Initialize Gemini with enhanced error handling
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel('gemini-1.5-pro')  # Using pro model for better reasoning
        # Test the model with a simple prompt
        test_response = gemini_model.generate_content("Test")
        if test_response.error:
            st.error(f"Gemini API test failed: {test_response.error}")
            gemini_model = None
        st.session_state.gemini_initialized = True
    except Exception as e:
        st.error(f"Failed to initialize Gemini API: {str(e)}")
        gemini_model = None
        st.session_state.gemini_initialized = False

    return supabase, gemini_model

supabase, gemini_model = initialize_services()

# Helper Functions
def display_connection_status():
    """Display connection status in the sidebar"""
    with st.sidebar:
        if st.session_state.supabase_connected:
            st.markdown('<div class="connection-status connected">✅ Connected to Supabase</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="connection-status disconnected">❌ Supabase Disconnected</div>', unsafe_allow_html=True)
            st.markdown('<div class="warning-box">Using mock data. Some features may be limited.</div>', unsafe_allow_html=True)
        
        if st.session_state.gemini_initialized:
            st.markdown('<div class="connection-status connected">✅ Gemini API Ready</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="connection-status disconnected">❌ Gemini API Unavailable</div>', unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def get_dynamic_categories(table, column, user_id, default_list):
    """Get dynamic categories from database or use defaults"""
    if not st.session_state.supabase_connected:
        return default_list
    
    try:
        response = supabase.table(table).select(column).eq('user_id', user_id).execute()
        if response.data:
            df = pd.DataFrame(response.data)
            categories = df[column].dropna().unique().tolist()
            return sorted(list(set(categories + default_list)))
        return default_list
    except Exception as e:
        st.error(f"Error fetching categories: {str(e)}")
        return default_list

def get_financial_data(table, user_id, date_range=None):
    """Generic function to get financial data with optional date range"""
    if not st.session_state.supabase_connected or st.session_state.mock_data:
        return pd.DataFrame()
    
    try:
        query = supabase.table(table).select('*').eq('user_id', user_id)
        
        if date_range:
            start_date, end_date = date_range
            query = query.gte('date', start_date.isoformat()).lte('date', end_date.isoformat())
        
        response = query.execute()
        return pd.DataFrame(response.data) if response.data else pd.DataFrame()
    except Exception as e:
        st.error(f"Error fetching {table} data: {str(e)}")
        return pd.DataFrame()

def generate_mock_data(data_type, rows=5):
    """Generate mock data for demo purposes"""
    today = datetime.now()
    if data_type == 'expenses':
        data = {
            'user_id': [1] * rows,
            'amount': np.random.uniform(5, 500, rows).round(2),
            'category': np.random.choice(DEFAULT_EXPENSE_CATEGORIES, rows),
            'date': pd.date_range(today - timedelta(days=30), periods=rows).strftime('%Y-%m-%d'),
            'payment_method': np.random.choice(DEFAULT_PAYMENT_METHODS, rows),
            'description': ['Mock data'] * rows,
            'fixed': np.random.choice([True, False], rows)
        }
    elif data_type == 'income':
        data = {
            'user_id': [1] * rows,
            'amount': np.random.uniform(500, 5000, rows).round(2),
            'source': np.random.choice(DEFAULT_INCOME_SOURCES, rows),
            'date': pd.date_range(today - timedelta(days=30), periods=rows).strftime('%Y-%m-%d'),
            'description': ['Mock data'] * rows,
            'fixed': np.random.choice([True, False], rows)
        }
    elif data_type == 'budgets':
        data = {
            'user_id': [1] * rows,
            'category': np.random.choice(DEFAULT_EXPENSE_CATEGORIES, rows),
            'amount': np.random.uniform(100, 1000, rows).round(2),
            'period': np.random.choice(['Monthly', 'Yearly'], rows),
            'start_date': pd.date_range(today, periods=rows).strftime('%Y-%m-%d')
        }
    elif data_type == 'goals':
        data = {
            'user_id': [1] * rows,
            'name': [f"Goal {i+1}" for i in range(rows)],
            'target_amount': np.random.uniform(1000, 10000, rows).round(2),
            'deadline': pd.date_range(today + timedelta(days=30), periods=rows).strftime('%Y-%m-%d'),
            'current_amount': np.random.uniform(0, 5000, rows).round(2)
        }
    elif data_type == 'investments':
        data = {
            'user_id': [1] * rows,
            'asset_name': [f"Asset {i+1}" for i in range(rows)],
            'amount': np.random.uniform(500, 5000, rows).round(2),
            'asset_type': np.random.choice(ASSET_TYPES, rows),
            'risk_level': np.random.choice(RISK_TOLERANCE_OPTIONS, rows),
            'date': pd.date_range(today - timedelta(days=30), periods=rows).strftime('%Y-%m-%d')
        }
    elif data_type == 'recurring':
        data = {
            'user_id': [1] * rows,
            'type': np.random.choice(['Expense', 'Income'], rows),
            'amount': np.random.uniform(50, 500, rows).round(2),
            'category': np.random.choice(DEFAULT_EXPENSE_CATEGORIES, rows),
            'frequency': np.random.choice(FREQUENCY_OPTIONS, rows),
            'start_date': pd.date_range(today, periods=rows).strftime('%Y-%m-%d')
        }
    return pd.DataFrame(data)

def calculate_financial_metrics(expenses_df, income_df):
    """Calculate key financial metrics"""
    metrics = {
        'total_expenses': expenses_df['amount'].sum() if 'amount' in expenses_df.columns and not expenses_df.empty else 0,
        'total_income': income_df['amount'].sum() if 'amount' in income_df.columns and not income_df.empty else 0,
        'fixed_expenses': expenses_df[expenses_df['fixed']]['amount'].sum() if 'amount' in expenses_df.columns and not expenses_df.empty else 0,
        'variable_expenses': expenses_df[~expenses_df['fixed']]['amount'].sum() if 'amount' in expenses_df.columns and not expenses_df.empty else 0,
        'fixed_income': income_df[income_df['fixed']]['amount'].sum() if 'amount' in income_df.columns and not income_df.empty else 0,
        'variable_income': income_df[~income_df['fixed']]['amount'].sum() if 'amount' in income_df.columns and not income_df.empty else 0,
    }
    metrics['net_income'] = metrics['total_income'] - metrics['total_expenses']
    metrics['savings_rate'] = (metrics['net_income'] / metrics['total_income'] * 100) if metrics['total_income'] > 0 else 0
    metrics['expense_ratio'] = (metrics['total_expenses'] / metrics['total_income'] * 100) if metrics['total_income'] > 0 else 0
    return metrics

def create_financial_charts(expenses_df, income_df):
    """Create financial visualization charts"""
    charts = {}
    if not expenses_df.empty and 'amount' in expenses_df.columns and 'category' in expenses_df.columns:
        cat_data = expenses_df.groupby('category')['amount'].sum().reset_index()
        charts['expense_by_category'] = px.pie(cat_data, values='amount', names='category', title="Expense Distribution",
                                              color_discrete_sequence=px.colors.sequential.Viridis)
        trend_data = expenses_df.groupby('date')['amount'].sum().reset_index()
        charts['expense_trend'] = px.line(trend_data, x='date', y='amount', title="Expense Trends",
                                         labels={'amount': 'Amount ($)', 'date': 'Date'})
    if not income_df.empty and 'amount' in income_df.columns and 'source' in income_df.columns:
        source_data = income_df.groupby('source')['amount'].sum().reset_index()
        charts['income_by_source'] = px.bar(source_data, x='source', y='amount', title="Income by Source",
                                           color='source', labels={'amount': 'Amount ($)', 'source': 'Income Source'})
        income_trend = income_df.groupby('date')['amount'].sum().reset_index()
        charts['income_trend'] = px.line(income_trend, x='date', y='amount', title="Income Trends",
                                        labels={'amount': 'Amount ($)', 'date': 'Date'})
    if not expenses_df.empty and not income_df.empty and 'amount' in expenses_df.columns and 'amount' in income_df.columns:
        cash_flow = pd.merge(expenses_df.groupby('date')['amount'].sum().reset_index(name='expenses'),
                             income_df.groupby('date')['amount'].sum().reset_index(name='income'),
                             on='date', how='outer').fillna(0)
        cash_flow['net'] = cash_flow['income'] - cash_flow['expenses']
        charts['cash_flow'] = px.line(cash_flow, x='date', y=['income', 'expenses', 'net'], title="Cash Flow",
                                     labels={'value': 'Amount ($)', 'date': 'Date', 'variable': 'Type'})
    return charts

def generate_pdf_report(report_type, user_id, start_date, end_date):
    """Generate PDF financial report"""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"{report_type} Financial Report", ln=1, align="C")
    try:
        expenses_df = get_financial_data('expenses', user_id, (start_date, end_date))
        income_df = get_financial_data('income', user_id, (start_date, end_date))
        metrics = calculate_financial_metrics(expenses_df, income_df)
        pdf.cell(200, 10, txt=f"Period: {start_date} to {end_date}", ln=1)
        pdf.cell(200, 10, txt=f"Total Income: ${metrics['total_income']:,.2f}", ln=1)
        pdf.cell(200, 10, txt=f"Total Expenses: ${metrics['total_expenses']:,.2f}", ln=1)
        pdf.cell(200, 10, txt=f"Net Income: ${metrics['net_income']:,.2f}", ln=1)
        pdf.cell(200, 10, txt=f"Savings Rate: {metrics['savings_rate']:.1f}%", ln=1)
        if not expenses_df.empty and 'category' in expenses_df.columns and 'amount' in expenses_df.columns:
            pdf.cell(200, 10, txt="Expense Breakdown:", ln=1)
            for cat, amt in expenses_df.groupby('category')['amount'].sum().items():
                pdf.cell(200, 10, txt=f"{cat}: ${amt:,.2f}", ln=1)
        if not income_df.empty and 'source' in income_df.columns and 'amount' in income_df.columns:
            pdf.cell(200, 10, txt="Income Breakdown:", ln=1)
            for src, amt in income_df.groupby('source')['amount'].sum().items():
                pdf.cell(200, 10, txt=f"{src}: ${amt:,.2f}", ln=1)
        return pdf.output(dest='S').encode('latin1')
    except Exception as e:
        st.error(f"Error generating report: {str(e)}")
        return None

def get_financial_advice(user_data, query):
    """Get enhanced financial advice from Gemini with robust error handling"""
    if not st.session_state.gemini_initialized:
        return "Financial advice unavailable. Gemini API not initialized. Please check your API key or configuration."
    
    try:
        prompt = f"""
        You are a highly experienced financial advisor with a deep understanding of personal finance. Provide detailed, actionable, and personalized advice based on the following:

        User Financial Data:
        - Monthly Income: ${user_data.get('total_income', 0):,.2f}
        - Monthly Expenses: ${user_data.get('total_expenses', 0):,.2f}
        - Savings Rate: {user_data.get('savings_rate', 0):.1f}%
        - Expense Categories: {', '.join(user_data.get('expense_categories', [])) or 'None'}
        - Income Sources: {', '.join(user_data.get('income_sources', [])) or 'None'}

        User Query: {query}

        Provide a response with:
        - A concise summary of the user's financial situation.
        - 3-5 specific, actionable recommendations in bullet points, tailored to the query.
        - A brief explanation of why each recommendation is suitable, considering the user's data.
        - Use a professional yet approachable tone.
        """
        response = gemini_model.generate_content(prompt)
        if response.error:
            return f"Error generating advice: {response.error}"
        return response.text
    except Exception as e:
        st.error(f"Error getting financial advice: {str(e)}")
        return "Unable to provide advice at this time due to an internal error. Please try again later."

# Dynamic Categories
current_user_id = 1  # In a real app, this would come from authentication
EXPENSE_CATEGORIES = get_dynamic_categories("expenses", "category", current_user_id, DEFAULT_EXPENSE_CATEGORIES)
PAYMENT_METHODS = get_dynamic_categories("expenses", "payment_method", current_user_id, DEFAULT_PAYMENT_METHODS)
INCOME_SOURCES = get_dynamic_categories("income", "source", current_user_id, DEFAULT_INCOME_SOURCES)

# Sidebar Navigation
with st.sidebar:
    st.markdown("<h1 style='text-align: center; color: #00CC96;'>💼 ProFinance</h1>", unsafe_allow_html=True)
    st.markdown("---")
    display_connection_status()
    menu_options = [
        "🏠 Dashboard",
        "💸 Expenses",
        "💵 Income",
        "📊 Budgets",
        "🎯 Goals",
        "📈 Analytics",
        "📑 Reports",
        "💰 Investments",
        "🔄 Recurring",
        "🧮 Financial Workbench",
        "🤖 Financial Advisor"
    ]
    selected_page = st.radio("Navigation", menu_options, label_visibility="hidden")
    st.markdown("---")
    st.subheader("Data Import")
    st.markdown("<div class='info-box'>Upload a CSV with columns: Type (Expense/Income), Amount, Category/Source, Date, Description, Payment Method, Fixed</div>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Upload Financial Data (CSV)", type=["csv"])
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file)
            required_columns = ['Type', 'Amount', 'Date']
            if all(col in df.columns for col in required_columns):
                st.success("File uploaded successfully!")
                if st.session_state.supabase_connected:
                    try:
                        expenses = df[df['Type'].str.lower() == 'expense']
                        income = df[df['Type'].str.lower() == 'income']
                        if not expenses.empty:
                            expenses.to_sql('expenses', supabase, if_exists='append', index=False)
                        if not income.empty:
                            income.to_sql('income', supabase, if_exists='append', index=False)
                        st.success("Data stored successfully!")
                        st.session_state.data_uploaded = True
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"Error storing data: {str(e)}")
                else:
                    st.warning("Data preview only (not stored - database not connected)")
                st.write("Data Preview:", df.head())
            else:
                st.error(f"Missing required columns. Needed: {', '.join(required_columns)}")
        except Exception as e:
            st.error(f"Error reading file: {str(e)}")
    st.markdown("---")
    st.markdown("<p style='text-align: center; color: grey;'>Made with ❤️ by ProFinance Team</p>", unsafe_allow_html=True)

# Main Content
st.markdown("<div class='main-header'>ProFinance Manager</div>", unsafe_allow_html=True)
current_page = selected_page.split()[1] if selected_page != "🧮 Financial Workbench" else "Financial Workbench"
if selected_page == "🤖 Financial Advisor":
    current_page = "Financial Advisor"

# Page Routing
if current_page == "Dashboard":
    st.markdown("<div class='section-header'>🏠 Dashboard</div>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    start_date = col1.date_input("Start Date", datetime.now() - timedelta(days=30))
    end_date = col2.date_input("End Date", datetime.now())
    expenses_df = get_financial_data('expenses', current_user_id, (start_date, end_date))
    income_df = get_financial_data('income', current_user_id, (start_date, end_date))
    if st.session_state.mock_data and (expenses_df.empty or income_df.empty):
        st.warning("Displaying mock data for demonstration purposes")
        expenses_df = generate_mock_data('expenses') if expenses_df.empty else expenses_df
        income_df = generate_mock_data('income') if income_df.empty else income_df
    metrics = calculate_financial_metrics(expenses_df, income_df)
    cols = st.columns(4)
    with cols[0]: st.markdown("<div class='metric-box'>", unsafe_allow_html=True); st.metric("Total Income", f"${metrics['total_income']:,.2f}"); st.markdown("</div>", unsafe_allow_html=True)
    with cols[1]: st.markdown("<div class='metric-box'>", unsafe_allow_html=True); st.metric("Total Expenses", f"${metrics['total_expenses']:,.2f}"); st.markdown("</div>", unsafe_allow_html=True)
    with cols[2]: st.markdown("<div class='metric-box'>", unsafe_allow_html=True); st.metric("Net Income", f"${metrics['net_income']:,.2f}"); st.markdown("</div>", unsafe_allow_html=True)
    with cols[3]: st.markdown("<div class='metric-box'>", unsafe_allow_html=True); st.metric("Savings Rate", f"{metrics['savings_rate']:.1f}%"); st.markdown("</div>", unsafe_allow_html=True)
    st.subheader("Quick Insights")
    if metrics['savings_rate'] < 10: st.warning("Your savings rate is low. Consider reducing discretionary spending or increasing income.")
    if metrics['expense_ratio'] > 80: st.warning("High expense ratio! More than 80% of your income is going to expenses.")
    if metrics['fixed_expenses'] / metrics['total_income'] > 0.5: st.warning("Your fixed expenses are high (>50% of income). Look for ways to reduce recurring costs.")
    st.subheader("Recent Transactions")
    if not expenses_df.empty or not income_df.empty:
        recent_expenses = expenses_df.sort_values('date', ascending=False).head(3) if 'date' in expenses_df.columns else pd.DataFrame()
        recent_income = income_df.sort_values('date', ascending=False).head(3) if 'date' in income_df.columns else pd.DataFrame()
        if not recent_expenses.empty: st.write("**Recent Expenses**"); st.dataframe(recent_expenses[['date', 'amount', 'category', 'payment_method']] if all(col in recent_expenses.columns for col in ['date', 'amount', 'category', 'payment_method']) else recent_expenses)
        if not recent_income.empty: st.write("**Recent Income**"); st.dataframe(recent_income[['date', 'amount', 'source']] if all(col in recent_income.columns for col in ['date', 'amount', 'source']) else recent_income)
    else: st.info("No transactions found for the selected period.")
    charts = create_financial_charts(expenses_df, income_df)
    for chart in charts.values(): st.plotly_chart(chart, use_container_width=True)

elif current_page == "Expenses":
    st.markdown("<div class='section-header'>💸 Expenses</div>", unsafe_allow_html=True)
    with st.expander("➕ Add New Expense", expanded=True):
        with st.form("expense_form", clear_on_submit=True):
            cols = st.columns(2)
            amount = cols[0].number_input("Amount ($)", min_value=0.01, step=0.01)
            date = cols[1].date_input("Date", datetime.now())
            category = st.selectbox("Category", EXPENSE_CATEGORIES + ["➕ Add New"])
            if category == "➕ Add New": category = st.text_input("New Category Name")
            payment_method = st.selectbox("Payment Method", PAYMENT_METHODS)
            description = st.text_input("Description (Optional)")
            fixed = st.checkbox("Fixed Expense (recurring)")
            submitted = st.form_submit_button("Add Expense")
            if submitted:
                if amount <= 0: st.error("Amount must be greater than 0")
                else:
                    if st.session_state.supabase_connected:
                        try:
                            data = {'user_id': current_user_id, 'amount': float(amount), 'category': category, 'date': date.strftime('%Y-%m-%d'),
                                    'payment_method': payment_method, 'description': description if description else None, 'fixed': fixed}
                            supabase.table('expenses').insert(data).execute()
                            st.success("Expense added successfully!")
                            time.sleep(1); st.rerun()
                        except Exception as e: st.error(f"Error adding expense: {str(e)}")
                    else: st.warning("Expense not saved (database not connected)")
    st.subheader("Expense Analysis")
    col1, col2 = st.columns(2)
    start_date = col1.date_input("Start Date", datetime.now() - timedelta(days=30))
    end_date = col2.date_input("End Date", datetime.now())
    expenses_df = get_financial_data('expenses', current_user_id, (start_date, end_date))
    if st.session_state.mock_data and expenses_df.empty: expenses_df = generate_mock_data('expenses', rows=15)
    if not expenses_df.empty and 'amount' in expenses_df.columns:
        total_spent = expenses_df['amount'].sum()
        avg_daily = total_spent / ((end_date - start_date).days + 1)
        st.markdown(f"**Total Spent:** ${total_spent:,.2f} | **Average Daily:** ${avg_daily:,.2f} | **Transactions:** {len(expenses_df)}")
        tab1, tab2, tab3 = st.tabs(["📊 Overview", "📅 Trends", "🔍 Details"])
        with tab1:
            if 'category' in expenses_df.columns:
                cat_data = expenses_df.groupby('category')['amount'].sum().reset_index()
                fig1 = px.pie(cat_data, values='amount', names='category', title="Expense Distribution by Category")
                st.plotly_chart(fig1, use_container_width=True)
            if 'payment_method' in expenses_df.columns:
                pm_data = expenses_df.groupby('payment_method')['amount'].sum().reset_index()
                fig2 = px.bar(pm_data, x='payment_method', y='amount', title="Expenses by Payment Method", color='payment_method')
                st.plotly_chart(fig2, use_container_width=True)
        with tab2:
            if 'date' in expenses_df.columns and 'amount' in expenses_df.columns:
                daily_data = expenses_df.groupby('date')['amount'].sum().reset_index()
                fig3 = px.line(daily_data, x='date', y='amount', title="Daily Expense Trend", markers=True)
                st.plotly_chart(fig3, use_container_width=True)
                weekly_data = expenses_df.copy(); weekly_data['date'] = pd.to_datetime(weekly_data['date'])
                weekly_data = weekly_data.set_index('date').resample('W')['amount'].sum().reset_index()
                fig4 = px.bar(weekly_data, x='date', y='amount', title="Weekly Expense Summary")
                st.plotly_chart(fig4, use_container_width=True)
        with tab3:
            st.dataframe(expenses_df.sort_values('date', ascending=False) if 'date' in expenses_df.columns else expenses_df)
            csv = expenses_df.to_csv(index=False).encode('utf-8')
            st.download_button("Export Expenses as CSV", csv, "expenses.csv", "text/csv", key='download-expenses-csv')
    else: st.info("No expenses found for the selected period."); fig = px.pie(names=["No Data"], values=[1], title="Expense Distribution"); st.plotly_chart(fig)

elif current_page == "Income":
    st.markdown("<div class='section-header'>💵 Income</div>", unsafe_allow_html=True)
    with st.expander("➕ Add New Income", expanded=True):
        with st.form("income_form", clear_on_submit=True):
            cols = st.columns(2)
            amount = cols[0].number_input("Amount ($)", min_value=0.01, step=0.01)
            date = cols[1].date_input("Date", datetime.now())
            source = st.selectbox("Source", INCOME_SOURCES + ["➕ Add New"])
            if source == "➕ Add New": source = st.text_input("New Source Name")
            description = st.text_input("Description (Optional)")
            fixed = st.checkbox("Fixed Income (recurring)")
            submitted = st.form_submit_button("Add Income")
            if submitted:
                if amount <= 0: st.error("Amount must be greater than 0")
                else:
                    if st.session_state.supabase_connected:
                        try:
                            data = {'user_id': current_user_id, 'amount': float(amount), 'source': source, 'date': date.strftime('%Y-%m-%d'),
                                    'description': description if description else None, 'fixed': fixed}
                            supabase.table('income').insert(data).execute()
                            st.success("Income added successfully!")
                            time.sleep(1); st.rerun()
                        except Exception as e: st.error(f"Error adding income: {str(e)}")
                    else: st.warning("Income not saved (database not connected)")
    st.subheader("Income Analysis")
    col1, col2 = st.columns(2)
    start_date = col1.date_input("Start Date", datetime.now() - timedelta(days=30))
    end_date = col2.date_input("End Date", datetime.now())
    income_df = get_financial_data('income', current_user_id, (start_date, end_date))
    if st.session_state.mock_data and income_df.empty: income_df = generate_mock_data('income', rows=15)
    if not income_df.empty and 'amount' in income_df.columns:
        total_income = income_df['amount'].sum()
        avg_daily = total_income / ((end_date - start_date).days + 1)
        st.markdown(f"**Total Income:** ${total_income:,.2f} | **Average Daily:** ${avg_daily:,.2f} | **Transactions:** {len(income_df)}")
        tab1, tab2 = st.tabs(["📊 Overview", "📅 Trends"])
        with tab1:
            if 'source' in income_df.columns:
                source_data = income_df.groupby('source')['amount'].sum().reset_index()
                fig = px.bar(source_data, x='source', y='amount', title="Income by Source", color='source')
                st.plotly_chart(fig, use_container_width=True)
        with tab2:
            if 'date' in income_df.columns and 'amount' in income_df.columns:
                trend_data = income_df.groupby('date')['amount'].sum().reset_index()
                fig = px.line(trend_data, x='date', y='amount', title="Income Trends", markers=True)
                st.plotly_chart(fig, use_container_width=True)
    else: st.info("No income found for the selected period."); fig = px.bar(x=["No Data"], y=[1], title="Income Sources"); st.plotly_chart(fig)

elif current_page == "Budgets":
    st.markdown("<div class='section-header'>📊 Budgets</div>", unsafe_allow_html=True)
    with st.expander("➕ Set Budget", expanded=True):
        with st.form("budget_form", clear_on_submit=True):
            category = st.selectbox("Category", EXPENSE_CATEGORIES)
            amount = st.number_input("Budget Amount ($)", min_value=0.01, step=0.01)
            period = st.selectbox("Period", ["Monthly", "Yearly"])
            submitted = st.form_submit_button("Set Budget")
            if submitted:
                if amount <= 0: st.error("Amount must be greater than 0")
                else:
                    if st.session_state.supabase_connected:
                        try:
                            data = {'user_id': current_user_id, 'category': category, 'amount': float(amount), 'period': period,
                                    'start_date': datetime.now().strftime('%Y-%m-%d')}
                            supabase.table('budgets').insert(data).execute()
                            st.success("Budget set successfully!")
                            time.sleep(1); st.rerun()
                        except Exception as e: st.error(f"Error setting budget: {str(e)}")
                    else: st.warning("Budget not saved (database not connected)")
    st.subheader("Budget Tracking")
    budgets_df = get_financial_data('budgets', current_user_id)
    if st.session_state.mock_data and budgets_df.empty: budgets_df = generate_mock_data('budgets', rows=5)
    if not budgets_df.empty and 'amount' in budgets_df.columns and 'category' in budgets_df.columns:
        for _, budget in budgets_df.iterrows():
            expenses_df = get_financial_data('expenses', current_user_id, (datetime.strptime(budget['start_date'], '%Y-%m-%d'), datetime.now()))
            spent = expenses_df[expenses_df['category'] == budget['category']]['amount'].sum() if 'amount' in expenses_df.columns and 'category' in expenses_df.columns else 0
            progress = (spent / budget['amount'] * 100) if budget['amount'] > 0 else 0
            st.markdown(f"<div class='metric-box'>", unsafe_allow_html=True)
            st.metric(f"{budget['category']} ({budget['period']})", f"${spent:,.2f} / ${budget['amount']:,.2f}", f"{progress:.1f}%")
            st.markdown("</div>", unsafe_allow_html=True)
            if progress > 100: st.warning(f"Over budget for {budget['category']}!")
    else: st.info("No budgets set."); fig = px.pie(names=["No Data"], values=[1], title="Budget Distribution"); st.plotly_chart(fig)

elif current_page == "Goals":
    st.markdown("<div class='section-header'>🎯 Goals</div>", unsafe_allow_html=True)
    with st.expander("➕ Set Financial Goal", expanded=True):
        with st.form("goal_form", clear_on_submit=True):
            name = st.text_input("Goal Name")
            target_amount = st.number_input("Target Amount ($)", min_value=0.01, step=0.01)
            deadline = st.date_input("Deadline", datetime.now() + timedelta(days=30))
            submitted = st.form_submit_button("Set Goal")
            if submitted:
                if target_amount <= 0: st.error("Amount must be greater than 0")
                else:
                    if st.session_state.supabase_connected:
                        try:
                            data = {'user_id': current_user_id, 'name': name, 'target_amount': float(target_amount),
                                    'deadline': deadline.strftime('%Y-%m-%d'), 'current_amount': 0}
                            supabase.table('goals').insert(data).execute()
                            st.success("Goal set successfully!")
                            time.sleep(1); st.rerun()
                        except Exception as e: st.error(f"Error setting goal: {str(e)}")
                    else: st.warning("Goal not saved (database not connected)")
    st.subheader("Goal Progress")
    goals_df = get_financial_data('goals', current_user_id)
    if st.session_state.mock_data and goals_df.empty: goals_df = generate_mock_data('goals', rows=3)
    if not goals_df.empty and 'target_amount' in goals_df.columns and 'current_amount' in goals_df.columns:
        for _, goal in goals_df.iterrows():
            progress = (goal['current_amount'] / goal['target_amount'] * 100) if goal['target_amount'] > 0 else 0
            st.markdown(f"<div class='metric-box'>", unsafe_allow_html=True)
            st.metric(goal['name'], f"${goal['current_amount']:,.2f} / ${goal['target_amount']:,.2f}", f"{progress:.1f}%")
            st.markdown("</div>", unsafe_allow_html=True)
            if progress >= 100: st.success(f"Goal '{goal['name']}' achieved!")
    else: st.info("No goals set."); fig = px.pie(names=["No Data"], values=[1], title="Goal Progress"); st.plotly_chart(fig)

elif current_page == "Analytics":
    st.markdown("<div class='section-header'>📈 Analytics</div>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    start_date = col1.date_input("Start Date", datetime.now() - timedelta(days=30))
    end_date = col2.date_input("End Date", datetime.now())
    expenses_df = get_financial_data('expenses', current_user_id, (start_date, end_date))
    income_df = get_financial_data('income', current_user_id, (start_date, end_date))
    if st.session_state.mock_data and (expenses_df.empty or income_df.empty):
        expenses_df = generate_mock_data('expenses') if expenses_df.empty else expenses_df
        income_df = generate_mock_data('income') if income_df.empty else income_df
    metrics = calculate_financial_metrics(expenses_df, income_df)
    st.markdown("<div class='metric-box'>", unsafe_allow_html=True); st.metric("Savings Rate", f"{metrics['savings_rate']:.1f}%"); st.markdown("</div>", unsafe_allow_html=True)
    tab1, tab2, tab3 = st.tabs(["📊 Expense Breakdown", "💰 Income Sources", "💸 Cash Flow"])
    with tab1: 
        if not expenses_df.empty and 'amount' in expenses_df.columns and 'category' in expenses_df.columns:
            fig = px.pie(expenses_df, values='amount', names='category', title="Expense Breakdown")
            st.plotly_chart(fig)
        else: st.info("No expense data."); fig = px.pie(names=["No Data"], values=[1]); st.plotly_chart(fig)
    with tab2: 
        if not income_df.empty and 'amount' in income_df.columns and 'source' in income_df.columns:
            fig = px.bar(income_df, x='source', y='amount', color='source', title="Income Sources")
            st.plotly_chart(fig)
        else: st.info("No income data."); fig = px.pie(names=["No Data"], values=[1]); st.plotly_chart(fig)
    with tab3: 
        if not expenses_df.empty and not income_df.empty and 'amount' in expenses_df.columns and 'amount' in income_df.columns:
            cash_flow = pd.merge(expenses_df.groupby('date')['amount'].sum().reset_index(name='expenses'),
                                 income_df.groupby('date')['amount'].sum().reset_index(name='income'),
                                 on='date', how='outer').fillna(0)
            cash_flow['net'] = cash_flow['income'] - cash_flow['expenses']
            fig = px.line(cash_flow, x='date', y=['income', 'expenses', 'net'], title="Cash Flow")
            st.plotly_chart(fig)
        else: st.info("No cash flow data."); fig = px.line(x=[0], y=[0], title="Cash Flow"); st.plotly_chart(fig)

elif current_page == "Reports":
    st.markdown("<div class='section-header'>📑 Reports</div>", unsafe_allow_html=True)
    report_type = st.selectbox("Report Type", ["Monthly", "Yearly", "Custom"])
    if report_type == "Custom":
        col1, col2 = st.columns(2)
        start_date = col1.date_input("Start Date", datetime.now() - timedelta(days=30))
        end_date = col2.date_input("End Date", datetime.now())
    else:
        start_date = datetime.now().replace(day=1).strftime('%Y-%m-%d') if report_type == "Monthly" else datetime.now().replace(month=1, day=1).strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')
    if st.button("Generate Report"):
        if st.session_state.supabase_connected:
            pdf_data = generate_pdf_report(report_type, current_user_id, start_date, end_date)
            if pdf_data: st.download_button("Download Report", pdf_data, f"{report_type}_report.pdf", "application/pdf")
        else: st.warning("Report generation unavailable (database not connected)")

elif current_page == "Investments":
    st.markdown("<div class='section-header'>💰 Investments</div>", unsafe_allow_html=True)
    with st.expander("➕ Add Investment", expanded=True):
        with st.form("investment_form", clear_on_submit=True):
            asset_name = st.text_input("Asset Name")
            amount = st.number_input("Amount ($)", min_value=0.01, step=0.01)
            asset_type = st.selectbox("Asset Type", ASSET_TYPES)
            risk_level = st.selectbox("Risk Level", RISK_TOLERANCE_OPTIONS)
            submitted = st.form_submit_button("Add Investment")
            if submitted:
                if amount <= 0: st.error("Amount must be greater than 0")
                else:
                    if st.session_state.supabase_connected:
                        try:
                            data = {'user_id': current_user_id, 'asset_name': asset_name, 'amount': float(amount), 'asset_type': asset_type,
                                    'risk_level': risk_level, 'date': datetime.now().strftime('%Y-%m-%d')}
                            supabase.table('investments').insert(data).execute()
                            st.success("Investment added successfully!")
                            time.sleep(1); st.rerun()
                        except Exception as e: st.error(f"Error adding investment: {str(e)}")
                    else: st.warning("Investment not saved (database not connected)")
    st.subheader("Investment Portfolio")
    investments_df = get_financial_data('investments', current_user_id)
    if st.session_state.mock_data and investments_df.empty: investments_df = generate_mock_data('investments', rows=5)
    if not investments_df.empty and 'amount' in investments_df.columns and 'asset_type' in investments_df.columns:
        total_invested = investments_df['amount'].sum()
        st.markdown(f"**Total Invested:** ${total_invested:,.2f}")
        fig = px.pie(investments_df, values='amount', names='asset_type', title="Portfolio Allocation")
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("No investments found."); fig = px.pie(names=["No Data"], values=[1], title="Portfolio Allocation"); st.plotly_chart(fig)

elif current_page == "Recurring":
    st.markdown("<div class='section-header'>🔄 Recurring Transactions</div>", unsafe_allow_html=True)
    with st.expander("➕ Add Recurring Transaction", expanded=True):
        with st.form("recurring_form", clear_on_submit=True):
            transaction_type = st.selectbox("Type", ["Expense", "Income"])
            amount = st.number_input("Amount ($)", min_value=0.01, step=0.01)
            category = st.selectbox("Category/Source", EXPENSE_CATEGORIES if transaction_type == "Expense" else INCOME_SOURCES)
            frequency = st.selectbox("Frequency", FREQUENCY_OPTIONS)
            start_date = st.date_input("Start Date", datetime.now())
            submitted = st.form_submit_button("Add Recurring Transaction")
            if submitted:
                if amount <= 0: st.error("Amount must be greater than 0")
                else:
                    if st.session_state.supabase_connected:
                        try:
                            data = {'user_id': current_user_id, 'type': transaction_type, 'amount': float(amount), 'category': category,
                                    'frequency': frequency, 'start_date': start_date.strftime('%Y-%m-%d')}
                            supabase.table('recurring').insert(data).execute()
                            st.success("Recurring transaction added successfully!")
                            time.sleep(1); st.rerun()
                        except Exception as e: st.error(f"Error adding recurring transaction: {str(e)}")
                    else: st.warning("Recurring transaction not saved (database not connected)")
    st.subheader("Recurring Transactions")
    recurring_df = get_financial_data('recurring', current_user_id)
    if st.session_state.mock_data and recurring_df.empty: recurring_df = generate_mock_data('recurring', rows=5)
    if not recurring_df.empty and 'amount' in recurring_df.columns and 'category' in recurring_df.columns:
        st.dataframe(recurring_df)
        fig = px.bar(recurring_df, x='category', y='amount', color='type', title="Recurring Transactions")
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("No recurring transactions found."); fig = px.bar(x=["No Data"], y=[1], title="Recurring Transactions"); st.plotly_chart(fig)

elif current_page == "Financial Workbench":
    st.markdown("<div class='section-header'>🧮 Financial Workbench</div>", unsafe_allow_html=True)
    st.subheader("Portfolio Optimization")
    investments_df = get_financial_data('investments', current_user_id)
    if st.session_state.mock_data and investments_df.empty: investments_df = generate_mock_data('investments', rows=5)
    if not investments_df.empty and 'amount' in investments_df.columns:
        def objective(weights): return -np.sum(investments_df['amount'] * weights)
        constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
        bounds = tuple((0, 1) for _ in range(len(investments_df)))
        initial_guess = [1./len(investments_df)] * len(investments_df)
        result = minimize(objective, initial_guess, method='SLSQP', bounds=bounds, constraints=constraints)
        if result.success:
            optimized_weights = result.x
            allocation = pd.DataFrame({'Asset': investments_df['asset_name'], 'Optimal Weight': optimized_weights})
            st.dataframe(allocation)
            fig = px.pie(allocation, values='Optimal Weight', names='Asset', title="Optimized Portfolio")
            st.plotly_chart(fig, use_container_width=True)
        else: st.warning("Optimization failed.")
    else: st.info("No investments for optimization."); fig = px.pie(names=["No Data"], values=[1], title="Optimized Portfolio"); st.plotly_chart(fig)

elif current_page == "Financial Advisor":
    st.markdown("<div class='section-header'>🤖 Financial Advisor</div>", unsafe_allow_html=True)
    # Get user financial data with fallback for empty DataFrames
    expenses_df = get_financial_data('expenses', current_user_id)
    income_df = get_financial_data('income', current_user_id)
    
    # Use mock data if real data is empty and mock_data is enabled
    if st.session_state.mock_data and (expenses_df.empty or income_df.empty):
        expenses_df = generate_mock_data('expenses') if expenses_df.empty else expenses_df
        income_df = generate_mock_data('income') if income_df.empty else income_df

    user_data = {
        "total_expenses": expenses_df['amount'].sum() if 'amount' in expenses_df.columns and not expenses_df.empty else 0,
        "total_income": income_df['amount'].sum() if 'amount' in income_df.columns and not income_df.empty else 0,
        "expense_categories": expenses_df['category'].unique().tolist() if 'category' in expenses_df.columns and not expenses_df.empty else [],
        "income_sources": income_df['source'].unique().tolist() if 'source' in income_df.columns and not income_df.empty else [],
        "savings_rate": ((income_df['amount'].sum() if 'amount' in income_df.columns and not income_df.empty else 0) - 
                         (expenses_df['amount'].sum() if 'amount' in expenses_df.columns and not expenses_df.empty else 0)) / 
                        (income_df['amount'].sum() if 'amount' in income_df.columns and not income_df.empty else 1) * 100 if 
                        (income_df['amount'].sum() if 'amount' in income_df.columns and not income_df.empty else 0) > 0 else 0
    }
    
    # Display financial snapshot
    with st.expander("📊 Your Financial Snapshot", expanded=True):
        cols = st.columns(2)
        cols[0].metric("Monthly Income", f"${user_data['total_income']:,.2f}")
        cols[1].metric("Monthly Expenses", f"${user_data['total_expenses']:,.2f}")
        cols[0].metric("Savings Rate", f"{user_data['savings_rate']:.1f}%")
        cols[1].metric("Net Income", f"${user_data['total_income'] - user_data['total_expenses']:,.2f}")
    
    # Financial advice interface
    st.subheader("Get Personalized Financial Advice")
    query = st.text_area("Ask me anything about your finances (e.g., 'How can I save more?', 'Should I invest in stocks?')")
    if st.button("Get Advice"):
        if query.strip():
            with st.spinner("Analyzing your finances and generating advice..."):
                advice = get_financial_advice(user_data, query)
                st.markdown(f"<div class='chat-bubble'>{advice}</div>", unsafe_allow_html=True)
        else:
            st.warning("Please enter a question or financial goal")

else:
    st.markdown(f"<div class='section-header'>{selected_page}</div>", unsafe_allow_html=True)
    st.info("This section is coming soon! Check back later for updates.")
