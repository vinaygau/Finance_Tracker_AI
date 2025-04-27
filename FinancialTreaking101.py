import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import io
import os
import numpy as np
import yfinance as yf
from fpdf import FPDF
from scipy.optimize import minimize
from supabase import create_client, Client
from tenacity import retry, stop_after_attempt, wait_fixed
import google.generativeai as genai
import json

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
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# Supabase and Gemini Configuration (use secrets)
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    SUPABASE_URL = "https://hugjvlpvxqvnkuzfyacw.supabase.co"
    SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh1Z2p2bHB2eHF2bmt1emZ5YWN3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDQ0Nzg4NDIsImV4cCI6MjA2MDA1NDg0Mn0.BDe2Wrr74P-pkR0XF6Sfgheq6k4Z0LvidHV-7JiDC30"
    GEMINI_API_KEY = "AIzaSyCgRp8oPIET2Y2tmOiC2PNhKjiV9vNxywU"
    st.warning("Using hardcoded credentials for local testing. Configure secrets in Streamlit Cloud for production.")

# Initialize Supabase client with retry logic
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def init_supabase():
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Test connection
        supabase.table('expenses').select('id').limit(1).execute()
        return supabase
    except Exception as e:
        st.error(f"Failed to connect to Supabase: {e}")
        return None

supabase = init_supabase()
if supabase is None:
    st.warning("Using mock data due to database connection issues.")

# Initialize Gemini API
try:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error(f"Failed to initialize Gemini API: {e}")
    gemini_model = None

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

# Helper Functions
@st.cache_data(ttl=3600)
def get_dynamic_categories(table, column, user_id, default_list):
    if supabase is None:
        return default_list
    try:
        response = supabase.table(table).select(column).eq('user_id', user_id).execute()
        if response.data:
            df = pd.DataFrame(response.data)
            categories = df[column].dropna().unique().tolist()
            return list(set(categories + default_list))
        return default_list
    except Exception as e:
        st.error(f"Error fetching categories: {e}")
        return default_list

@st.cache_data(ttl=3600)
def get_monthly_expenses(user_id, month):
    if supabase is None:
        return 0
    try:
        response = supabase.rpc('get_monthly_expenses', {'user_id': user_id, 'month': month}).execute()
        return response.data[0]['total'] if response.data else 0
    except Exception as e:
        st.error(f"Error fetching monthly expenses: {e}")
        return 0

@st.cache_data(ttl=3600)
def get_monthly_income(user_id, month):
    if supabase is None:
        return 0
    try:
        response = supabase.rpc('get_monthly_income', {'user_id': user_id, 'month': month}).execute()
        return response.data[0]['total'] if response.data else 0
    except Exception as e:
        st.error(f"Error fetching monthly income: {e}")
        return 0

def analyze_and_store_data(df, user_id):
    try:
        for index, row in df.iterrows():
            data_type = row.get('Type', '').lower()
            if data_type == 'expense':
                expense_data = {
                    'user_id': user_id,
                    'amount': float(row.get('Amount', 0)),
                    'category': row.get('Category', 'Other'),
                    'date': row.get('Date', datetime.now().strftime('%Y-%m-%d')),
                    'description': row.get('Description', None),
                    'payment_method': row.get('Payment Method', 'Cash'),
                    'fixed': bool(row.get('Fixed', False))
                }
                supabase.table('expenses').insert(expense_data).execute()
            elif data_type == 'income':
                income_data = {
                    'user_id': user_id,
                    'amount': float(row.get('Amount', 0)),
                    'source': row.get('Source', 'Other'),
                    'date': row.get('Date', datetime.now().strftime('%Y-%m-%d')),
                    'description': row.get('Description', None),
                    'fixed': bool(row.get('Fixed', False))
                }
                supabase.table('income').insert(income_data).execute()
        st.success("Data analyzed and stored successfully!")
        st.cache_data.clear()  # Clear cache to refresh categories
        return True
    except Exception as e:
        st.error(f"Error analyzing and storing data: {e}")
        return False

def generate_pdf_report(report_type, user_id, start_date, end_date):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"{report_type} Financial Report", ln=1, align="C")
    
    try:
        expenses = supabase.table('expenses').select('amount,category,date').eq('user_id', user_id).gte('date', start_date).lte('date', end_date).execute()
        income = supabase.table('income').select('amount,source,date').eq('user_id', user_id).gte('date', start_date).lte('date', end_date).execute()
        
        expenses_df = pd.DataFrame(expenses.data) if expenses.data else pd.DataFrame()
        income_df = pd.DataFrame(income.data) if income.data else pd.DataFrame()
        
        total_expenses = expenses_df['amount'].sum() if not expenses_df.empty else 0
        total_income = income_df['amount'].sum() if not income_df.empty else 0
        
        pdf.cell(200, 10, txt=f"Period: {start_date} to {end_date}", ln=1)
        pdf.cell(200, 10, txt=f"Total Income: ${total_income:,.2f}", ln=1)
        pdf.cell(200, 10, txt=f"Total Expenses: ${total_expenses:,.2f}", ln=1)
        pdf.cell(200, 10, txt=f"Net: ${(total_income - total_expenses):,.2f}", ln=1)
        
        if not expenses_df.empty:
            pdf.cell(200, 10, txt="Expense Breakdown:", ln=1)
            for cat, amt in expenses_df.groupby('category')['amount'].sum().items():
                pdf.cell(200, 10, txt=f"{cat}: ${amt:,.2f}", ln=1)
        
        if not income_df.empty:
            pdf.cell(200, 10, txt="Income Breakdown:", ln=1)
            for src, amt in income_df.groupby('source')['amount'].sum().items():
                pdf.cell(200, 10, txt=f"{src}: ${amt:,.2f}", ln=1)
        
        return pdf.output(dest='S').encode('latin1')
    except Exception as e:
        st.error(f"Error generating report: {e}")
        return None

def get_financial_advice(user_data, query):
    if gemini_model is None:
        return "Unable to provide advice due to API initialization issues."
    try:
        prompt = f"""
        You are a financial advisor. Provide accurate, actionable, and concise advice based on the user's financial data and query.
        Financial Data: {json.dumps(user_data, indent=2)}
        Query: {query}
        """
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        st.error(f"Error fetching financial advice: {e}")
        return "Unable to provide advice at this time."

# Dynamic Categories
current_user_id = 1  # Default user
EXPENSE_CATEGORIES = get_dynamic_categories("expenses", "category", current_user_id, DEFAULT_EXPENSE_CATEGORIES)
PAYMENT_METHODS = get_dynamic_categories("expenses", "payment_method", current_user_id, DEFAULT_PAYMENT_METHODS)
INCOME_SOURCES = get_dynamic_categories("income", "source", current_user_id, DEFAULT_INCOME_SOURCES)

# Sidebar Navigation
with st.sidebar:
    st.markdown("<h1 style='text-align: center; color: #00CC96;'>💼 ProFinance</h1>", unsafe_allow_html=True)
    st.markdown("---")
    
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
    st.markdown("<div class='info-box'>Upload a CSV with columns: Type (Expense/Income), Amount, Category, Source, Date, Description, Payment Method, Fixed</div>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Upload Financial Data (CSV)", type=["csv"])
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file)
            st.success("File uploaded successfully!")
            st.write("Preview:", df.head())
            if analyze_and_store_data(df, current_user_id):
                st.session_state['data_uploaded'] = True
        except Exception as e:
            st.error(f"Error reading file: {e}")
    
    st.markdown("---")
    st.markdown("<p style='text-align: center; color: grey;'>Made with ❤️ by xAI</p>", unsafe_allow_html=True)

# Get Current Page
current_page = selected_page.split()[1] if selected_page != "🧮 Financial Workbench" else "Financial Workbench"
if selected_page == "🤖 Financial Advisor":
    current_page = "Financial Advisor"

# Main Content
st.markdown("<div class='main-header'>ProFinance Manager</div>", unsafe_allow_html=True)

if current_page == "Dashboard":
    st.markdown("<div class='section-header'>🏠 Dashboard</div>", unsafe_allow_html=True)
    today = datetime.now()
    current_month = today.strftime("%Y-%m")
    last_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    
    cols = st.columns(4)
    with cols[0]:
        monthly_spending = get_monthly_expenses(current_user_id, current_month)
        last_month_spending = get_monthly_expenses(current_user_id, last_month)
        change = ((monthly_spending - last_month_spending) / last_month_spending * 100) if last_month_spending else 0
        st.markdown("<div class='metric-box'>", unsafe_allow_html=True)
        st.metric("Monthly Spending", f"${monthly_spending:,.2f}", f"{change:.1f}%")
        st.markdown("</div>", unsafe_allow_html=True)
    
    with cols[1]:
        monthly_income = get_monthly_income(current_user_id, current_month)
        last_month_income = get_monthly_income(current_user_id, last_month)
        income_change = ((monthly_income - last_month_income) / last_month_income * 100) if last_month_income else 0
        st.markdown("<div class='metric-box'>", unsafe_allow_html=True)
        st.metric("Monthly Income", f"${monthly_income:,.2f}", f"{income_change:.1f}%")
        st.markdown("</div>", unsafe_allow_html=True)
    
    with cols[2]:
        savings_rate = ((monthly_income - monthly_spending) / monthly_income * 100) if monthly_income > 0 else 0
        st.markdown("<div class='metric-box'>", unsafe_allow_html=True)
        st.metric("Savings Rate", f"{savings_rate:.1f}%")
        st.markdown("</div>", unsafe_allow_html=True)
    
    with cols[3]:
        expense_ratio = (monthly_spending / monthly_income * 100) if monthly_income > 0 else 0
        st.markdown("<div class='metric-box'>", unsafe_allow_html=True)
        st.metric("Expense Ratio", f"{expense_ratio:.1f}%")
        st.markdown("</div>", unsafe_allow_html=True)
    
    st.subheader("Quick Insights")
    if expense_ratio > 80:
        st.warning("High expense ratio! Consider reducing discretionary spending.")
    if savings_rate < 10:
        st.warning("Low savings rate! Aim to save at least 10-20% of your income.")
    
    # Recent Transactions
    st.subheader("Recent Transactions")
    if supabase:
        try:
            expenses = supabase.table('expenses').select('amount,category,date').eq('user_id', current_user_id).order('date', desc=True).limit(5).execute()
            income = supabase.table('income').select('amount,source,date').eq('user_id', current_user_id).order('date', desc=True).limit(5).execute()
            transactions = pd.concat([
                pd.DataFrame(expenses.data).assign(Type='Expense') if expenses.data else pd.DataFrame(),
                pd.DataFrame(income.data).assign(Type='Income') if income.data else pd.DataFrame()
            ]).sort_values('date', ascending=False).head(5)
            if not transactions.empty:
                st.dataframe(transactions)
            else:
                st.info("No recent transactions.")
        except Exception as e:
            st.error(f"Error fetching recent transactions: {e}")

elif current_page == "Expenses":
    st.markdown("<div class='section-header'>💸 Expenses</div>", unsafe_allow_html=True)
    with st.expander("Add New Expense", expanded=True):
        with st.form("expense_form"):
            amount = st.number_input("Amount ($)", min_value=0.01, step=0.01)
            category = st.selectbox("Category", EXPENSE_CATEGORIES + ["Add New"])
            if category == "Add New":
                category = st.text_input("New Category")
            date = st.date_input("Date", datetime.now())
            payment_method = st.selectbox("Payment Method", PAYMENT_METHODS)
            description = st.text_input("Description (Optional)")
            fixed = st.checkbox("Fixed Expense")
            submitted = st.form_submit_button("Add Expense")
            if submitted and supabase:
                try:
                    data = {
                        'user_id': current_user_id,
                        'amount': amount,
                        'category': category,
                        'date': date.strftime('%Y-%m-%d'),
                        'payment_method': payment_method,
                        'description': description if description else None,
                        'fixed': fixed
                    }
                    supabase.table('expenses').insert(data).execute()
                    st.success("Expense added!")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Error adding expense: {e}")
    
    st.subheader("Expense Analysis")
    col1, col2 = st.columns(2)
    start_date = col1.date_input("Start Date", datetime.now() - timedelta(days=30))
    end_date = col2.date_input("End Date", datetime.now())
    
    if supabase:
        try:
            response = supabase.table('expenses').select('*').eq('user_id', current_user_id).gte('date', start_date.isoformat()).lte('date', end_date.isoformat()).execute()
            expenses_df = pd.DataFrame(response.data) if response.data else pd.DataFrame()
            
            if not expenses_df.empty:
                total_spent = expenses_df['amount'].sum()
                fixed_expenses = expenses_df[expenses_df['fixed']]['amount'].sum()
                variable_expenses = total_spent - fixed_expenses
                avg_daily = total_spent / ((end_date - start_date).days + 1)
                
                st.markdown(f"""
                    **Total Spent:** ${total_spent:,.2f} | 
                    **Fixed:** ${fixed_expenses:,.2f} | 
                    **Variable:** ${variable_expenses:,.2f} | 
                    **Avg Daily:** ${avg_daily:,.2f}
                """)
                
                st.dataframe(expenses_df)
                
                tab1, tab2, tab3 = st.tabs(["By Category", "By Payment Method", "Trends"])
                with tab1:
                    cat_data = expenses_df.groupby('category')['amount'].sum().reset_index()
                    fig = px.pie(cat_data, values='amount', names='category', title="Expense Distribution", color_discrete_sequence=px.colors.sequential.Viridis)
                    st.plotly_chart(fig)
                
                with tab2:
                    pm_data = expenses_df.groupby('payment_method')['amount'].sum().reset_index()
                    fig = px.bar(pm_data, x='payment_method', y='amount', title="Expenses by Payment Method", color='payment_method')
                    st.plotly_chart(fig)
                
                with tab3:
                    trend_data = expenses_df.groupby('date')['amount'].sum().reset_index()
                    fig = px.line(trend_data, x='date', y='amount', title="Expense Trends")
                    st.plotly_chart(fig)
            else:
                st.info("No expenses found for the selected period.")
        except Exception as e:
            st.error(f"Error fetching expenses: {e}")
    else:
        st.warning("Expenses cannot be displayed due to database issues.")

elif current_page == "Income":
    st.markdown("<div class='section-header'>💵 Income</div>", unsafe_allow_html=True)
    with st.expander("Add New Income", expanded=True):
        with st.form("income_form"):
            amount = st.number_input("Amount ($)", min_value=0.01, step=0.01)
            source = st.selectbox("Source", INCOME_SOURCES + ["Add New"])
            if source == "Add New":
                source = st.text_input("New Source")
            date = st.date_input("Date", datetime.now())
            description = st.text_input("Description (Optional)")
            fixed = st.checkbox("Fixed Income")
            submitted = st.form_submit_button("Add Income")
            if submitted and supabase:
                try:
                    data = {
                        'user_id': current_user_id,
                        'amount': amount,
                        'source': source,
                        'date': date.strftime('%Y-%m-%d'),
                        'description': description if description else None,
                        'fixed': fixed
                    }
                    supabase.table('income').insert(data).execute()
                    st.success("Income added!")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Error adding income: {e}")
    
    st.subheader("Income Analysis")
    col1, col2 = st.columns(2)
    start_date = col1.date_input("Start Date", datetime.now() - timedelta(days=30))
    end_date = col2.date_input("End Date", datetime.now())
    
    if supabase:
        try:
            response = supabase.table('income').select('*').eq('user_id', current_user_id).gte('date', start_date.isoformat()).lte('date', end_date.isoformat()).execute()
            income_df = pd.DataFrame(response.data) if response.data else pd.DataFrame()
            
            if not income_df.empty:
                total_income = income_df['amount'].sum()
                fixed_income = income_df[income_df['fixed']]['amount'].sum()
                variable_income = total_income - fixed_income
                avg_daily = total_income / ((end_date - start_date).days + 1)
                
                st.markdown(f"""
                    **Total Income:** ${total_income:,.2f} | 
                    **Fixed:** ${fixed_income:,.2f} | 
                    **Variable:** ${variable_income:,.2f} | 
                    **Avg Daily:** ${avg_daily:,.2f}
                """)
                
                st.dataframe(income_df)
                
                tab1, tab2 = st.tabs(["By Source", "Trends"])
                with tab1:
                    source_data = income_df.groupby('source')['amount'].sum().reset_index()
                    fig = px.bar(source_data, x='source', y='amount', title="Income by Source", color='source')
                    st.plotly_chart(fig)
                
                with tab2:
                    trend_data = income_df.groupby('date')['amount'].sum().reset_index()
                    fig = px.line(trend_data, x='date', y='amount', title="Income Trends")
                    st.plotly_chart(fig)
            else:
                st.info("No income found for the selected period.")
        except Exception as e:
            st.error(f"Error fetching income: {e}")
    else:
        st.warning("Income cannot be displayed due to database issues.")

elif current_page == "Budgets":
    st.markdown("<div class='section-header'>📊 Budgets</div>", unsafe_allow_html=True)
    with st.expander("Set Budget", expanded=True):
        with st.form("budget_form"):
            category = st.selectbox("Category", EXPENSE_CATEGORIES)
            amount = st.number_input("Budget Amount ($)", min_value=0.01, step=0.01)
            period = st.selectbox("Period", ["Monthly", "Yearly"])
            submitted = st.form_submit_button("Set Budget")
            if submitted and supabase:
                try:
                    data = {
                        'user_id': current_user_id,
                        'category': category,
                        'amount': amount,
                        'period': period,
                        'start_date': datetime.now().strftime('%Y-%m-%d')
                    }
                    supabase.table('budgets').insert(data).execute()
                    st.success("Budget set!")
                except Exception as e:
                    st.error(f"Error setting budget: {e}")
    
    st.subheader("Budget Tracking")
    if supabase:
        try:
            budgets = supabase.table('budgets').select('*').eq('user_id', current_user_id).execute()
            budgets_df = pd.DataFrame(budgets.data) if budgets.data else pd.DataFrame()
            if not budgets_df.empty:
                for _, budget in budgets_df.iterrows():
                    expenses = supabase.table('expenses').select('amount').eq('user_id', current_user_id).eq('category', budget['category']).gte('date', budget['start_date']).execute()
                    spent = sum(item['amount'] for item in expenses.data) if expenses.data else 0
                    st.markdown(f"<div class='metric-box'>", unsafe_allow_html=True)
                    st.metric(f"{budget['category']} ({budget['period']})", f"${spent:,.2f} / ${budget['amount']:,.2f}", f"{(spent / budget['amount'] * 100):.1f}%")
                    st.markdown("</div>", unsafe_allow_html=True)
                    if spent > budget['amount']:
                        st.warning(f"Over budget for {budget['category']}!")
            else:
                st.info("No budgets set.")
        except Exception as e:
            st.error(f"Error fetching budgets: {e}")
    else:
        st.warning("Budgets cannot be displayed due to database issues.")

elif current_page == "Goals":
    st.markdown("<div class='section-header'>🎯 Goals</div>", unsafe_allow_html=True)
    with st.expander("Set Financial Goal", expanded=True):
        with st.form("goal_form"):
            name = st.text_input("Goal Name")
            target_amount = st.number_input("Target Amount ($)", min_value=0.01, step=0.01)
            deadline = st.date_input("Deadline")
            submitted = st.form_submit_button("Set Goal")
            if submitted and supabase:
                try:
                    data = {
                        'user_id': current_user_id,
                        'name': name,
                        'target_amount': target_amount,
                        'deadline': deadline.strftime('%Y-%m-%d'),
                        'current_amount': 0
                    }
                    supabase.table('goals').insert(data).execute()
                    st.success("Goal set!")
                except Exception as e:
                    st.error(f"Error setting goal: {e}")
    
    st.subheader("Goal Progress")
    if supabase:
        try:
            goals = supabase.table('goals').select('*').eq('user_id', current_user_id).execute()
            goals_df = pd.DataFrame(goals.data) if goals.data else pd.DataFrame()
            if not goals_df.empty:
                for _, goal in goals_df.iterrows():
                    progress = (goal['current_amount'] / goal['target_amount'] * 100) if goal['target_amount'] > 0 else 0
                    st.markdown(f"<div class='metric-box'>", unsafe_allow_html=True)
                    st.metric(goal['name'], f"${goal['current_amount']:,.2f} / ${goal['target_amount']:,.2f}", f"{progress:.1f}%")
                    st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.info("No goals set.")
        except Exception as e:
            st.error(f"Error fetching goals: {e}")
    else:
        st.warning("Goals cannot be displayed due to database issues.")

elif current_page == "Analytics":
    st.markdown("<div class='section-header'>📈 Analytics</div>", unsafe_allow_html=True)
    if st.session_state.get('data_uploaded', False) or supabase:
        st.subheader("Financial Analysis")
        col1, col2 = st.columns(2)
        start_date = col1.date_input("Start Date", datetime.now() - timedelta(days=30))
        end_date = col2.date_input("End Date", datetime.now())
        
        if supabase:
            try:
                expenses = supabase.table('expenses').select('*').eq('user_id', current_user_id).gte('date', start_date.isoformat()).lte('date', end_date.isoformat()).execute()
                income = supabase.table('income').select('*').eq('user_id', current_user_id).gte('date', start_date.isoformat()).lte('date', end_date.isoformat()).execute()
                
                expenses_df = pd.DataFrame(expenses.data) if expenses.data else pd.DataFrame()
                income_df = pd.DataFrame(income.data) if income.data else pd.DataFrame()
                
                if not expenses_df.empty or not income_df.empty:
                    total_expenses = expenses_df['amount'].sum() if not expenses_df.empty else 0
                    total_income = income_df['amount'].sum() if not income_df.empty else 0
                    savings_rate = ((total_income - total_expenses) / total_income * 100) if total_income > 0 else 0
                    
                    st.markdown("<div class='metric-box'>", unsafe_allow_html=True)
                    st.metric("Savings Rate", f"{savings_rate:.1f}%")
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                    tab1, tab2, tab3 = st.tabs(["Expense Breakdown", "Income Sources", "Cash Flow"])
                    with tab1:
                        if not expenses_df.empty:
                            fig = px.pie(expenses_df, values='amount', names='category', title="Expense Breakdown", color_discrete_sequence=px.colors.sequential.Plasma)
                            st.plotly_chart(fig)
                    
                    with tab2:
                        if not income_df.empty:
                            fig = px.bar(income_df, x='date', y='amount', color='source', title="Income Over Time")
                            st.plotly_chart(fig)
                    
                    with tab3:
                        if not expenses_df.empty and not income_df.empty:
                            cash_flow = pd.merge(
                                expenses_df.groupby('date')['amount'].sum().reset_index(name='expenses'),
                                income_df.groupby('date')['amount'].sum().reset_index(name='income'),
                                on='date', how='outer'
                            ).fillna(0)
                            cash_flow['net'] = cash_flow['income'] - cash_flow['expenses']
                            fig = px.line(cash_flow, x='date', y=['income', 'expenses', 'net'], title="Cash Flow")
                            st.plotly_chart(fig)
                else:
                    st.info("No data available for the selected period.")
            except Exception as e:
                st.error(f"Error fetching analytics data: {e}")
        else:
            st.warning("Analytics cannot be displayed due to database issues.")

elif current_page == "Reports":
    st.markdown("<div class='section-header'>📑 Reports</div>", unsafe_allow_html=True)
    report_type = st.selectbox("Report Type", ["Monthly", "Yearly", "Custom"])
    if report_type == "Custom":
        col1, col2 = st.columns(2)
        start_date = col1.date_input("Start Date", datetime.now() - timedelta(days=30))
        end_date = col2.date_input("End Date", datetime.now())
    else:
        start_date = datetime.now().strftime("%Y-%m-01") if report_type == "Monthly" else datetime.now().strftime("%Y-01-01")
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    if st.button("Generate Report"):
        if supabase:
            pdf_data = generate_pdf_report(report_type, current_user_id, start_date, end_date)
            if pdf_data:
                st.download_button(
                    label=f"Download {report_type} Report",
                    data=pdf_data,
                    file_name=f"{report_type}_Financial_Report.pdf",
                    mime="application/pdf"
                )
        else:
            st.warning("Report generation unavailable due to database issues.")

elif current_page == "Investments":
    st.markdown("<div class='section-header'>💰 Investments</div>", unsafe_allow_html=True)
    with st.expander("Add Investment", expanded=True):
        with st.form("investment_form"):
            asset_name = st.text_input("Asset Name")
            amount = st.number_input("Amount ($)", min_value=0.01, step=0.01)
            asset_type = st.selectbox("Asset Type", ASSET_TYPES)
            risk_level = st.selectbox("Risk Level", RISK_TOLERANCE_OPTIONS)
            submitted = st.form_submit_button("Add Investment")
            if submitted and supabase:
                try:
                    data = {
                        'user_id': current_user_id,
                        'asset_name': asset_name,
                        'amount': amount,
                        'asset_type': asset_type,
                        'risk_level': risk_level,
                        'date': datetime.now().strftime('%Y-%m-%d')
                    }
                    supabase.table('investments').insert(data).execute()
                    st.success("Investment added!")
                except Exception as e:
                    st.error(f"Error adding investment: {e}")
    
    st.subheader("Investment Portfolio")
    if supabase:
        try:
            investments = supabase.table('investments').select('*').eq('user_id', current_user_id).execute()
            investments_df = pd.DataFrame(investments.data) if investments.data else pd.DataFrame()
            if not investments_df.empty:
                st.dataframe(investments_df)
                fig = px.pie(investments_df, values='amount', names='asset_type', title="Portfolio Allocation", color_discrete_sequence=px.colors.sequential.Magma)
                st.plotly_chart(fig)
            else:
                st.info("No investments found.")
        except Exception as e:
            st.error(f"Error fetching investments: {e}")
    else:
        st.warning("Investments cannot be displayed due to database issues.")

elif current_page == "Recurring":
    st.markdown("<div class='section-header'>🔄 Recurring Transactions</div>", unsafe_allow_html=True)
    with st.expander("Add Recurring Transaction", expanded=True):
        with st.form("recurring_form"):
            transaction_type = st.selectbox("Type", ["Expense", "Income"])
            amount = st.number_input("Amount ($)", min_value=0.01, step=0.01)
            category = st.selectbox("Category/Source", EXPENSE_CATEGORIES if transaction_type == "Expense" else INCOME_SOURCES)
            frequency = st.selectbox("Frequency", FREQUENCY_OPTIONS)
            start_date = st.date_input("Start Date", datetime.now())
            submitted = st.form_submit_button("Add Recurring Transaction")
            if submitted and supabase:
                try:
                    data = {
                        'user_id': current_user_id,
                        'type': transaction_type,
                        'amount': amount,
                        'category': category,
                        'frequency': frequency,
                        'start_date': start_date.strftime('%Y-%m-%d')
                    }
                    supabase.table('recurring').insert(data).execute()
                    st.success("Recurring transaction added!")
                except Exception as e:
                    st.error(f"Error adding recurring transaction: {e}")
    
    st.subheader("Recurring Transactions")
    if supabase:
        try:
            recurring = supabase.table('recurring').select('*').eq('user_id', current_user_id).execute()
            recurring_df = pd.DataFrame(recurring.data) if recurring.data else pd.DataFrame()
            if not recurring_df.empty:
                st.dataframe(recurring_df)
            else:
                st.info("No recurring transactions found.")
        except Exception as e:
            st.error(f"Error fetching recurring transactions: {e}")
    else:
        st.warning("Recurring transactions cannot be displayed due to database issues.")

elif current_page == "Financial Workbench":
    st.markdown("<div class='section-header'>🧮 Financial Workbench</div>", unsafe_allow_html=True)
    st.subheader("Portfolio Optimization")
    if supabase:
        try:
            response = supabase.table('investments').select('asset_name,amount').eq('user_id', current_user_id).execute()
            investments = pd.DataFrame(response.data) if response.data else pd.DataFrame()
            
            if not investments.empty:
                def objective(weights):
                    return -np.sum(investments['amount'] * weights)  # Maximize return (simplified)
                
                constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
                bounds = tuple((0, 1) for _ in range(len(investments)))
                initial_guess = [1./len(investments)] * len(investments)
                
                result = minimize(
                    objective,
                    initial_guess,
                    method='SLSQP',
                    bounds=bounds,
                    constraints=constraints
                )
                
                if result.success:
                    optimized_weights = result.x
                    allocation = pd.DataFrame({
                        'Asset': investments['asset_name'],
                        'Optimal Weight': optimized_weights
                    })
                    st.write("Optimized Portfolio Allocation")
                    st.dataframe(allocation)
                    fig = px.pie(allocation, values='Optimal Weight', names='Asset', title="Optimized Portfolio", color_discrete_sequence=px.colors.sequential.Inferno)
                    st.plotly_chart(fig)
                else:
                    st.warning("Optimization failed.")
            else:
                st.info("No investments available for optimization.")
        except Exception as e:
            st.error(f"Error optimizing portfolio: {e}")
    else:
        st.warning("Portfolio optimization unavailable due to database issues.")

elif current_page == "Financial Advisor":
    st.markdown("<div class='section-header'>🤖 Financial Advisor</div>", unsafe_allow_html=True)
    st.subheader("Ask Gemini for Financial Advice")
    
    if supabase:
        try:
            expenses = supabase.table('expenses').select('amount,category,date').eq('user_id', current_user_id).execute()
            income = supabase.table('income').select('amount,source,date').eq('user_id', current_user_id).execute()
            expenses_df = pd.DataFrame(expenses.data) if expenses.data else pd.DataFrame()
            income_df = pd.DataFrame(income.data) if income.data else pd.DataFrame()
            
            user_data = {
                "total_expenses": expenses_df['amount'].sum() if not expenses_df.empty else 0,
                "total_income": income_df['amount'].sum() if not income_df.empty else 0,
                "expense_categories": expenses_df['category'].unique().tolist() if not expenses_df.empty else [],
                "income_sources": income_df['source'].unique().tolist() if not income_df.empty else [],
                "savings_rate": ((income_df['amount'].sum() - expenses_df['amount'].sum()) / income_df['amount'].sum() * 100) if income_df['amount'].sum() > 0 else 0
            }
        except Exception as e:
            st.error(f"Error fetching user data: {e}")
            user_data = {}
    else:
        user_data = {}
    
    query = st.text_area("Enter your financial question or goal (e.g., 'How can I save more?', 'Should I invest in stocks?')")
    if st.button("Get Advice"):
        if query:
            advice = get_financial_advice(user_data, query)
            st.markdown(f"<div class='chat-bubble'>{advice}</div>", unsafe_allow_html=True)
        else:
            st.warning("Please enter a question or goal.")
else:
    st.markdown(f"<div class='section-header'>{selected_page}</div>", unsafe_allow_html=True)
    st.write("This section is under development.")
