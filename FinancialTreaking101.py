import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import io
import time
import os
import numpy as np
import yfinance as yf
from fpdf import FPDF
from scipy.optimize import minimize
from supabase import create_client, Client

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
    }
    .section-header {
        font-size: 24px;
        font-weight: bold;
        color: #636EFA;
        border-bottom: 2px solid #636EFA;
        padding-bottom: 5px;
    }
    .stButton>button {
        background-color: #00CC96;
        color: white;
        border-radius: 5px;
        padding: 10px 20px;
        font-weight: bold;
    }
    .stButton>button:hover {
        background-color: #009973;
    }
    .metric-box {
        background-color: #f9f9f9;
        padding: 10px;
        border-radius: 5px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# Supabase Configuration
SUPABASE_URL = "https://hugjvlpvxqvnkuzfyacw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh1Z2p2bHB2eHF2bmt1emZ5YWN3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDQ0Nzg4NDIsImV4cCI6MjA2MDA1NDg0Mn0.BDe2Wrr74P-pkR0XF6Sfgheq6k4Z0LvidHV-7JiDC30"

# Initialize Supabase client
@st.cache_resource(ttl=3600)
def init_supabase():
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        return supabase
    except Exception as e:
        st.error(f"Failed to connect to Supabase: {e}")
        return None

supabase = init_supabase()
if supabase is None:
    st.error("Application cannot run without database connection.")
    st.stop()

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
def get_dynamic_categories(table, column, user_id, default_list):
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

def get_last_month():
    today = datetime.now()
    first_day = today.replace(day=1)
    last_month = first_day - timedelta(days=1)
    return last_month.strftime("%Y-%m")

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
        return True
    except Exception as e:
        st.error(f"Error analyzing and storing data: {e}")
        return False

def generate_pdf_report(report_type, user_id):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"{report_type} Financial Report", ln=1, align="C")
    
    if report_type == "Monthly":
        period = datetime.now().strftime("%Y-%m")
    elif report_type == "Yearly":
        period = datetime.now().strftime("%Y")
    
    try:
        expenses = supabase.table('expenses').select('amount,category,date').eq('user_id', user_id).like('date', f"{period}%").execute()
        income = supabase.table('income').select('amount,source,date').eq('user_id', user_id).like('date', f"{period}%").execute()
        
        expenses_df = pd.DataFrame(expenses.data) if expenses.data else pd.DataFrame()
        income_df = pd.DataFrame(income.data) if income.data else pd.DataFrame()
        
        total_expenses = expenses_df['amount'].sum() if not expenses_df.empty else 0
        total_income = income_df['amount'].sum() if not income_df.empty else 0
        
        pdf.cell(200, 10, txt=f"Total Income: ${total_income:,.2f}", ln=1)
        pdf.cell(200, 10, txt=f"Total Expenses: ${total_expenses:,.2f}", ln=1)
        pdf.cell(200, 10, txt=f"Net: ${(total_income - total_expenses):,.2f}", ln=1)
        
        if not expenses_df.empty:
            pdf.cell(200, 10, txt="Expense Breakdown:", ln=1)
            for cat, amt in expenses_df.groupby('category')['amount'].sum().items():
                pdf.cell(200, 10, txt=f"{cat}: ${amt:,.2f}", ln=1)
        
        return pdf.output(dest='S').encode('latin1')
    except Exception as e:
        st.error(f"Error generating report: {e}")
        return None

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
        "🧮 Financial Workbench"
    ]
    selected_page = st.radio("Navigation", menu_options, label_visibility="hidden")
    
    st.markdown("---")
    st.subheader("Data Import")
    uploaded_file = st.file_uploader("Upload Financial Data (CSV)", type=["csv"])
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        st.success("File uploaded successfully!")
        st.write("Preview:", df.head())
        if analyze_and_store_data(df, current_user_id):
            st.session_state['data_uploaded'] = True
    
    st.markdown("---")
    st.markdown("<p style='text-align: center; color: grey;'>Made with ❤️ by xAI</p>", unsafe_allow_html=True)

# Get Current Page
current_page = selected_page.split()[1] if selected_page != "🧮 Financial Workbench" else "Financial Workbench"

# Main Content
st.markdown("<div class='main-header'>ProFinance Manager</div>", unsafe_allow_html=True)

if current_page == "Dashboard":
    st.markdown("<div class='section-header'>🏠 Dashboard</div>", unsafe_allow_html=True)
    today = datetime.now()
    current_month = today.strftime("%Y-%m")
    last_month = get_last_month()
    
    cols = st.columns(4)
    with cols[0]:
        monthly_spending = supabase.rpc('get_monthly_expenses', {'user_id': current_user_id, 'month': current_month}).execute().data[0]['total'] if supabase.rpc('get_monthly_expenses', {'user_id': current_user_id, 'month': current_month}).execute().data else 0
        last_month_spending = supabase.rpc('get_monthly_expenses', {'user_id': current_user_id, 'month': last_month}).execute().data[0]['total'] if supabase.rpc('get_monthly_expenses', {'user_id': current_user_id, 'month': last_month}).execute().data else 0
        change = ((monthly_spending - last_month_spending) / last_month_spending * 100) if last_month_spending else 0
        st.markdown("<div class='metric-box'>", unsafe_allow_html=True)
        st.metric("Monthly Spending", f"${monthly_spending:,.2f}", f"{change:.1f}%")
        st.markdown("</div>", unsafe_allow_html=True)
    
    with cols[1]:
        monthly_income = supabase.rpc('get_monthly_income', {'user_id': current_user_id, 'month': current_month}).execute().data[0]['total'] if supabase.rpc('get_monthly_income', {'user_id': current_user_id, 'month': current_month}).execute().data else 0
        last_month_income = supabase.rpc('get_monthly_income', {'user_id': current_user_id, 'month': last_month}).execute().data[0]['total'] if supabase.rpc('get_monthly_income', {'user_id': current_user_id, 'month': last_month}).execute().data else 0
        income_change = ((monthly_income - last_month_income) / last_month_income * 100) if last_month_income else 0
        st.markdown("<div class='metric-box'>", unsafe_allow_html=True)
        st.metric("Monthly Income", f"${monthly_income:,.2f}", f"{income_change:.1f}%")
        st.markdown("</div>", unsafe_allow_html=True)
    
    with cols[2]:
        profit = monthly_income - monthly_spending
        last_month_profit = last_month_income - last_month_spending
        profit_change = ((profit - last_month_profit) / last_month_profit * 100) if last_month_profit else 0
        st.markdown("<div class='metric-box'>", unsafe_allow_html=True)
        st.metric("Monthly Profit", f"${profit:,.2f}", f"{profit_change:.1f}%")
        st.markdown("</div>", unsafe_allow_html=True)
    
    with cols[3]:
        savings_response = supabase.rpc('get_savings_progress', {'user_id': current_user_id}).execute()
        savings = savings_response.data[0]['saved'] if savings_response.data else 0
        target = savings_response.data[0]['target'] if savings_response.data else 0
        progress = (savings / target * 100) if target else 0
        st.markdown("<div class='metric-box'>", unsafe_allow_html=True)
        st.metric("Savings Progress", f"${savings:,.2f}", f"{progress:.1f}% of ${target:,.2f}")
        st.markdown("</div>", unsafe_allow_html=True)

elif current_page == "Analytics":
    st.markdown("<div class='section-header'>📈 Analytics</div>", unsafe_allow_html=True)
    if st.session_state.get('data_uploaded', False):
        st.write("Analyzing uploaded data...")
        expenses = supabase.table('expenses').select('*').eq('user_id', current_user_id).execute()
        income = supabase.table('income').select('*').eq('user_id', current_user_id).execute()
        
        expenses_df = pd.DataFrame(expenses.data) if expenses.data else pd.DataFrame()
        income_df = pd.DataFrame(income.data) if income.data else pd.DataFrame()
        
        if not expenses_df.empty:
            fig_exp = px.pie(expenses_df, values='amount', names='category', title="Expense Breakdown")
            st.plotly_chart(fig_exp)
        
        if not income_df.empty:
            fig_inc = px.bar(income_df, x='date', y='amount', color='source', title="Income Over Time")
            st.plotly_chart(fig_inc)
    else:
        st.info("Please upload a CSV file to analyze your financial data.")

elif current_page == "Reports":
    st.markdown("<div class='section-header'>📑 Reports</div>", unsafe_allow_html=True)
    report_type = st.selectbox("Select Report Type", ["Monthly", "Yearly"])
    if st.button("Generate Report"):
        pdf_data = generate_pdf_report(report_type, current_user_id)
        if pdf_data:
            st.download_button(
                label=f"Download {report_type} Report",
                data=pdf_data,
                file_name=f"{report_type}_Financial_Report.pdf",
                mime="application/pdf"
            )

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
            submitted = st.form_submit_button("Add Expense")
            if submitted:
                data = {
                    'user_id': current_user_id,
                    'amount': amount,
                    'category': category,
                    'date': date.strftime('%Y-%m-%d'),
                    'payment_method': payment_method
                }
                supabase.table('expenses').insert(data).execute()
                st.success("Expense added!")

    expenses = supabase.table('expenses').select('*').eq('user_id', current_user_id).execute()
    if expenses.data:
        st.dataframe(pd.DataFrame(expenses.data))

elif current_page == "Income":
    st.markdown("<div class='section-header'>💵 Income</div>", unsafe_allow_html=True)
    with st.expander("Add New Income", expanded=True):
        with st.form("income_form"):
            amount = st.number_input("Amount ($)", min_value=0.01, step=0.01)
            source = st.selectbox("Source", INCOME_SOURCES + ["Add New"])
            if source == "Add New":
                source = st.text_input("New Source")
            date = st.date_input("Date", datetime.now())
            submitted = st.form_submit_button("Add Income")
            if submitted:
                data = {
                    'user_id': current_user_id,
                    'amount': amount,
                    'source': source,
                    'date': date.strftime('%Y-%m-%d')
                }
                supabase.table('income').insert(data).execute()
                st.success("Income added!")

    income = supabase.table('income').select('*').eq('user_id', current_user_id).execute()
    if income.data:
        st.dataframe(pd.DataFrame(income.data))

# Placeholder for other sections
elif current_page in ["Budgets", "Goals", "Investments", "Recurring", "Financial Workbench"]:
    st.markdown(f"<div class='section-header'>{selected_page}</div>", unsafe_allow_html=True)
    st.write("This section is under development.")
