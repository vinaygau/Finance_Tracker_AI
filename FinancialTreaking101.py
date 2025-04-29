import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import os
import numpy as np
from supabase import create_client, Client
from tenacity import retry, stop_after_attempt, wait_fixed
import time

# Constants
DEFAULT_EXPENSE_CATEGORIES = ["Housing", "Food", "Transportation", "Utilities", "Healthcare",
                             "Entertainment", "Education", "Personal", "Debt Payments",
                             "Savings", "Investments", "Gifts", "Other"]
DEFAULT_PAYMENT_METHODS = ["Cash", "Credit Card", "Debit Card", "Bank Transfer", "Digital Wallet", "Check"]
DEFAULT_INCOME_SOURCES = ["Salary", "Freelance", "Investments", "Rental", "Business", "Gifts", "Other"]

# Initialize session state
if 'data_uploaded' not in st.session_state:
    st.session_state.data_uploaded = False
if 'supabase_connected' not in st.session_state:
    st.session_state.supabase_connected = False
if 'mock_data' not in st.session_state:
    st.session_state.mock_data = False
if 'tables_created' not in st.session_state:
    st.session_state.tables_created = False

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

# Initialize Supabase
def initialize_services():
    # Fetch credentials from secrets or environment variables
    try:
        SUPABASE_URL = st.secrets["https://qkeyjzxnhnosdlxtwsbm.supabase.co"]
        SUPABASE_KEY = st.secrets["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFrZXlqenhuaG5vc2RseHR3c2JtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDE4OTAzNzIsImV4cCI6MjA1NzQ2NjM3Mn0.DsxE9-sTfF0hYaSitoq8uExpk7rusH0NlxqXLGy-G2U"]
        st.session_state.using_secrets = True
    except (KeyError, FileNotFoundError):
        SUPABASE_URL = os.getenv("SUPABASE_URL", "")
        SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
        st.session_state.using_secrets = False

    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("Supabase credentials not found. Using mock data only.")
        st.session_state.supabase_connected = False
        st.session_state.mock_data = True
        return None

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(3))
    def init_supabase(url, key):
        try:
            supabase = create_client(url, key)
            # Test connection by querying a simple table
            response = supabase.table('expenses').select('id', count='exact').limit(1).execute()
            if hasattr(response, 'error') and response.error:
                if 'relation "public.expenses" does not exist' in str(response.error):
                    st.warning("Required tables not found. Attempting to create database schema...")
                    if create_tables(supabase):
                        st.session_state.tables_created = True
                        st.success("Database tables created successfully!")
                    else:
                        st.error("Failed to create tables. Check Supabase configuration.")
                        return None
                else:
                    st.error(f"Supabase connection error: {response.error.message}")
                    return None
            st.session_state.supabase_connected = True
            return supabase
        except Exception as e:
            st.error(f"Supabase connection failed: {str(e)}. Retrying...")
            return None

    def create_tables(supabase):
        try:
            tables = [
                """
                CREATE TABLE IF NOT EXISTS public.expenses (
                    id bigserial PRIMARY KEY,
                    user_id bigint NOT NULL,
                    amount numeric NOT NULL,
                    category text NOT NULL,
                    date date NOT NULL,
                    payment_method text NOT NULL,
                    description text,
                    fixed boolean DEFAULT false,
                    created_at timestamp with time zone DEFAULT now()
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS public.income (
                    id bigserial PRIMARY KEY,
                    user_id bigint NOT NULL,
                    amount numeric NOT NULL,
                    source text NOT NULL,
                    date date NOT NULL,
                    description text,
                    fixed boolean DEFAULT false,
                    created_at timestamp with time zone DEFAULT now()
                );
                """,
                """
                ALTER TABLE public.expenses ENABLE ROW LEVEL SECURITY;
                ALTER TABLE public.income ENABLE ROW LEVEL SECURITY;
                """
            ]
            for sql in tables:
                result = supabase.rpc('execute', {'sql': sql}).execute()
                if hasattr(result, 'error') and result.error:
                    st.error(f"Error executing SQL: {result.error.message}")
                    return False
            return True
        except Exception as e:
            st.error(f"Error creating tables: {str(e)}")
            return False

    supabase = init_supabase(SUPABASE_URL, SUPABASE_KEY)
    if not supabase:
        st.session_state.supabase_connected = False
        st.session_state.mock_data = True
        st.warning("Supabase connection failed. Using mock data only.")
    else:
        st.session_state.mock_data = False

    return supabase

supabase = initialize_services()

# Helper Functions
def display_connection_status():
    with st.sidebar:
        if st.session_state.supabase_connected:
            status = f"""
            <div class="connection-status connected">
                ✅ Connected to Supabase
                {f"<br><small>Tables created: {st.session_state.tables_created}</small>" if hasattr(st.session_state, 'tables_created') else ""}
            </div>
            """
            st.markdown(status, unsafe_allow_html=True)
        else:
            st.markdown('<div class="connection-status disconnected">❌ Supabase Disconnected</div>', unsafe_allow_html=True)
            if st.session_state.mock_data:
                st.markdown('<div class="warning-box">Using mock data. Some features may be limited.</div>', unsafe_allow_html=True)
            if st.button("Retry Connection", key="retry_connection"):
                st.rerun()

@st.cache_data(ttl=3600)
def get_dynamic_categories(table, column, user_id, default_list):
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
    return pd.DataFrame(data)

def calculate_financial_metrics(expenses_df, income_df):
    metrics = {
        'total_expenses': expenses_df['amount'].sum() if 'amount' in expenses_df.columns and not expenses_df.empty else 0,
        'total_income': income_df['amount'].sum() if 'amount' in income_df.columns and not income_df.empty else 0,
        'fixed_expenses': expenses_df[expenses_df['fixed']]['amount'].sum() if 'amount' in expenses_df.columns and 'fixed' in expenses_df.columns and not expenses_df.empty else 0,
        'variable_expenses': expenses_df[~expenses_df['fixed']]['amount'].sum() if 'amount' in expenses_df.columns and 'fixed' in expenses_df.columns and not expenses_df.empty else 0,
        'fixed_income': income_df[income_df['fixed']]['amount'].sum() if 'amount' in income_df.columns and 'fixed' in income_df.columns and not income_df.empty else 0,
        'variable_income': income_df[~income_df['fixed']]['amount'].sum() if 'amount' in income_df.columns and 'fixed' in income_df.columns and not income_df.empty else 0,
    }
    metrics['net_income'] = metrics['total_income'] - metrics['total_expenses']
    metrics['savings_rate'] = (metrics['net_income'] / metrics['total_income'] * 100) if metrics['total_income'] > 0 else 0
    metrics['expense_ratio'] = (metrics['total_expenses'] / metrics['total_income'] * 100) if metrics['total_income'] > 0 else 0
    return metrics

def create_financial_charts(expenses_df, income_df):
    charts = {}
    if not expenses_df.empty and 'amount' in expenses_df.columns and 'category' in expenses_df.columns:
        cat_data = expenses_df.groupby('category')['amount'].sum().reset_index()
        charts['expense_by_category'] = px.pie(cat_data, values='amount', names='category', title="Expense Distribution",
                                             color_discrete_sequence=px.colors.sequential.Viridis)
    if not expenses_df.empty and 'amount' in expenses_df.columns and 'date' in expenses_df.columns:
        trend_data = expenses_df.groupby('date')['amount'].sum().reset_index()
        charts['expense_trend'] = px.line(trend_data, x='date', y='amount', title="Expense Trends",
                                        labels={'amount': 'Amount ($)', 'date': 'Date'})
    if not income_df.empty and 'amount' in income_df.columns and 'source' in income_df.columns:
        source_data = income_df.groupby('source')['amount'].sum().reset_index()
        charts['income_by_source'] = px.bar(source_data, x='source', y='amount', title="Income by Source",
                                          color='source', labels={'amount': 'Amount ($)', 'source': 'Income Source'})
    if not income_df.empty and 'amount' in income_df.columns and 'date' in income_df.columns:
        income_trend = income_df.groupby('date')['amount'].sum().reset_index()
        charts['income_trend'] = px.line(income_trend, x='date', y='amount', title="Income Trends",
                                       labels={'amount': 'Amount ($)', 'date': 'Date'})
    return charts

# Dynamic Categories
current_user_id = 1
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
                            supabase.table('expenses').insert(expenses.to_dict('records')).execute()
                        if not income.empty:
                            supabase.table('income').insert(income.to_dict('records')).execute()
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
current_page = selected_page.split()[1]

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
    st.subheader("Recent Transactions")
    if not expenses_df.empty or not income_df.empty:
        recent_expenses = expenses_df.sort_values('date', ascending=False).head(3) if 'date' in expenses_df.columns else pd.DataFrame()
        recent_income = income_df.sort_values('date', ascending=False).head(3) if 'date' in income_df.columns else pd.DataFrame()
        if not recent_expenses.empty and 'date' in recent_expenses.columns and 'amount' in recent_expenses.columns and 'category' in recent_expenses.columns and 'payment_method' in recent_expenses.columns:
            st.write("**Recent Expenses**"); st.dataframe(recent_expenses[['date', 'amount', 'category', 'payment_method']])
        if not recent_income.empty and 'date' in recent_income.columns and 'amount' in recent_income.columns and 'source' in recent_income.columns:
            st.write("**Recent Income**"); st.dataframe(recent_income[['date', 'amount', 'source']])
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
    expenses_df = get_financial_data('expenses', current_user_id, (-receptor_date, end_date))
    if st.session_state.mock_data and expenses_df.empty: expenses_df = generate_mock_data('expenses', rows=15)
    if not expenses_df.empty and 'amount' in expenses_df.columns:
        total_spent = expenses_df['amount'].sum()
        avg_daily = total_spent / ((end_date - start_date).days + 1) if (end_date - start_date).days + 1 > 0 else 0
        st.markdown(f"**Total Spent:** ${total_spent:,.2f} | **Average Daily:** ${avg_daily:,.2f} | **Transactions:** {len(expenses_df)}")
        tab1, tab2 = st.tabs(["📊 Overview", "📅 Trends"])
        with tab1:
            if 'category' in expenses_df.columns and 'amount' in expenses_df.columns:
                cat_data = expenses_df.groupby('category')['amount'].sum().reset_index()
                fig1 = px.pie(cat_data, values='amount', names='category', title="Expense Distribution by Category")
                st.plotly_chart(fig1, use_container_width=True)
            if 'payment_method' in expenses_df.columns and 'amount' in expenses_df.columns:
                pm_data = expenses_df.groupby('payment_method')['amount'].sum().reset_index()
                fig2 = px.bar(pm_data, x='payment_method', y='amount', title="Expenses by Payment Method")
                st.plotly_chart(fig2, use_container_width=True)
        with tab2:
            if 'date' in expenses_df.columns and 'amount' in expenses_df.columns:
                trend_data = expenses_df.groupby('date')['amount'].sum().reset_index()
                fig3 = px.line(trend_data, x='date', y='amount', title="Expense Trends")
                st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("No expenses found for the selected period.")

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
        avg_daily = total_income / ((end_date - start_date).days + 1) if (end_date - start_date).days + 1 > 0 else 0
        st.markdown(f"**Total Income:** ${total_income:,.2f} | **Average Daily:** ${avg_daily:,.2f} | **Transactions:** {len(income_df)}")
        tab1, tab2 = st.tabs(["📊 Overview", "📅 Trends"])
        with tab1:
            if 'source' in income_df.columns and 'amount' in income_df.columns:
                source_data = income_df.groupby('source')['amount'].sum().reset_index()
                fig1 = px.pie(source_data, values='amount', names='source', title="Income Distribution by Source")
                st.plotly_chart(fig1, use_container_width=True)
        with tab2:
            if 'date' in income_df.columns and 'amount' in income_df.columns:
                trend_data = income_df.groupby('date')['amount'].sum().reset_index()
                fig2 = px.line(trend_data, x='date', y='amount', title="Income Trends")
                st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No income found for the selected period.")
