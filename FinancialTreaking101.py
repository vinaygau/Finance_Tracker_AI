import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import mysql.connector
from mysql.connector import Error
import io
import time
import os
import numpy as np
import yfinance as yf
from fpdf import FPDF
from scipy.optimize import minimize

# Database Configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'root',  # Update to your MySQL password
    'database': 'finance_db'
}

# Initialize database connection
@st.cache_resource(ttl=3600)
def init_db():
    retries = 3
    delay = 1
    
    for attempt in range(retries):
        try:
            conn = mysql.connector.connect(
                host=DB_CONFIG['host'],
                user=DB_CONFIG['user'],
                password=DB_CONFIG['password'],
                database=DB_CONFIG['database'],
                connection_timeout=5
            )
            if conn.is_connected():
                st.success("Connected to MySQL database successfully!")
                return conn
        except Error as e:
            st.warning(f"MySQL connection attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
    
    st.error("Failed to connect to MySQL database after multiple attempts")
    return None

# Initialize database connection
conn = init_db()
if conn is None:
    st.error("Application cannot run without database connection.")
    st.stop()

# Create tables if they don't exist
def create_tables(connection):
    try:
        cursor = connection.cursor()
        
        # Users table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) NOT NULL UNIQUE,
            password VARCHAR(255) NOT NULL
        )
        """)
        
        # Expenses table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            expense_id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            amount DECIMAL(10,2) NOT NULL,
            category VARCHAR(50) NOT NULL,
            subcategory VARCHAR(50),
            date DATE NOT NULL,
            description TEXT,
            payment_method VARCHAR(50) NOT NULL,
            fixed BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """)
        
        # Budgets table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            budget_id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            category VARCHAR(50) NOT NULL,
            subcategory VARCHAR(50),
            limit_amount DECIMAL(10,2) NOT NULL,
            period VARCHAR(20) NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """)
        
        # Savings goals table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS savings_goals (
            goal_id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            goal_name VARCHAR(100) NOT NULL,
            target_amount DECIMAL(10,2) NOT NULL,
            current_amount DECIMAL(10,2) NOT NULL,
            target_date DATE NOT NULL,
            priority INT NOT NULL,
            description TEXT,
            risk_tolerance VARCHAR(20) NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """)
        
        # Income table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS income (
            income_id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            amount DECIMAL(10,2) NOT NULL,
            source VARCHAR(50) NOT NULL,
            date DATE NOT NULL,
            description TEXT,
            fixed BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """)
        
        # Investments table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS investments (
            inv_id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            asset_name VARCHAR(100) NOT NULL,
            amount_invested DECIMAL(10,2) NOT NULL,
            current_value DECIMAL(10,2) NOT NULL,
            purchase_date DATE NOT NULL,
            asset_type VARCHAR(50) NOT NULL,
            risk_level VARCHAR(20) NOT NULL,
            expected_return DECIMAL(5,2) NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """)
        
        # Recurring transactions table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS recurring (
            rec_id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            type VARCHAR(20) NOT NULL,
            amount DECIMAL(10,2) NOT NULL,
            category VARCHAR(50) NOT NULL,
            frequency VARCHAR(20) NOT NULL,
            next_date DATE NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """)
        
        # Financial ratios table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS financial_ratios (
            ratio_id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            date DATE NOT NULL,
            ratio_name VARCHAR(50) NOT NULL,
            ratio_value DECIMAL(10,2) NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """)
        
        # Optimization results table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS optimization_results (
            opt_id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            date DATE NOT NULL,
            category VARCHAR(50) NOT NULL,
            recommended_amount DECIMAL(10,2) NOT NULL,
            savings_potential DECIMAL(10,2) NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """)
        
        # Add default user if not exists
        cursor.execute("INSERT IGNORE INTO users (user_id, username, password) VALUES (1, 'user1', 'pass1')")
        
        connection.commit()
        cursor.close()
        
    except Error as e:
        st.error(f"Error creating tables: {e}")

# Create tables on startup
create_tables(conn)

# Page configuration
st.set_page_config(
    page_title="ProFinance Manager",
    layout="wide",
    initial_sidebar_state="expanded"
)

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

# Helper functions
def get_dynamic_categories(conn, table, column, user_id, default_list):
    try:
        query = f"SELECT DISTINCT {column} FROM {table} WHERE user_id = %s AND {column} IS NOT NULL"
        df = pd.read_sql(query, conn, params=(user_id,))
        categories = df[column].tolist()
        return list(set(categories + default_list))
    except Error as e:
        st.error(f"Error fetching categories: {e}")
        return default_list

def get_last_month():
    today = datetime.now()
    first_day = today.replace(day=1)
    last_month = first_day - timedelta(days=1)
    return last_month.strftime("%Y-%m")

# Financial analysis functions
def calculate_financial_ratios(conn, user_id):
    try:
        current_month = datetime.now().strftime("%Y-%m")
        
        # Get monthly income
        monthly_income = pd.read_sql(
            "SELECT COALESCE(SUM(amount), 0) as total FROM income WHERE user_id = %s AND DATE_FORMAT(date, '%%Y-%%m') = %s",
            conn, params=(user_id, current_month)
        ).iloc[0,0]
        
        # Get monthly expenses
        monthly_expenses = pd.read_sql(
            "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = %s AND DATE_FORMAT(date, '%%Y-%%m') = %s",
            conn, params=(user_id, current_month)
        ).iloc[0,0]
        
        # Get investment value
        total_assets = pd.read_sql(
            "SELECT COALESCE(SUM(current_value), 0) as total FROM investments WHERE user_id = %s",
            conn, params=(user_id,)
        ).iloc[0,0]
        
        # Calculate ratios
        savings_rate = ((monthly_income - monthly_expenses) / monthly_income * 100) if monthly_income > 0 else 0
        expense_ratio = (monthly_expenses / monthly_income * 100) if monthly_income > 0 else 0
        net_worth = total_assets
        
        # Store ratios in database
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO financial_ratios (user_id, date, ratio_name, ratio_value) VALUES (%s, %s, %s, %s)",
            (user_id, datetime.now().date(), 'Savings Rate', savings_rate)
        )
        cursor.execute(
            "INSERT INTO financial_ratios (user_id, date, ratio_name, ratio_value) VALUES (%s, %s, %s, %s)",
            (user_id, datetime.now().date(), 'Expense Ratio', expense_ratio)
        )
        cursor.execute(
            "INSERT INTO financial_ratios (user_id, date, ratio_name, ratio_value) VALUES (%s, %s, %s, %s)",
            (user_id, datetime.now().date(), 'Net Worth', net_worth)
        )
        conn.commit()
        cursor.close()
        
        return {
            'savings_rate': savings_rate,
            'expense_ratio': expense_ratio,
            'net_worth': net_worth
        }
        
    except Error as e:
        st.error(f"Error calculating financial ratios: {e}")
        return None

def optimize_budget(conn, user_id):
    try:
        expenses = pd.read_sql(
            "SELECT category, SUM(amount) as total FROM expenses WHERE user_id = %s AND date >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH) GROUP BY category",
            conn, params=(user_id,)
        )
        
        if expenses.empty:
            return None
        
        # Simple optimization: reduce spending by 10% in each category
        recommendations = []
        for _, row in expenses.iterrows():
            recommended = row['total'] * 0.9
            savings = row['total'] - recommended
            recommendations.append({
                'category': row['category'],
                'recommended_amount': recommended,
                'savings_potential': savings
            })
        
        # Store results
        cursor = conn.cursor()
        for rec in recommendations:
            cursor.execute(
                "INSERT INTO optimization_results (user_id, date, category, recommended_amount, savings_potential) VALUES (%s, %s, %s, %s, %s)",
                (user_id, datetime.now().date(), rec['category'], rec['recommended_amount'], rec['savings_potential'])
            )
        conn.commit()
        cursor.close()
        
        return recommendations
    
    except Error as e:
        st.error(f"Error optimizing budget: {e}")
        return None

# Get dynamic categories
current_user_id = 1  # Default user
EXPENSE_CATEGORIES = get_dynamic_categories(conn, "expenses", "category", current_user_id, DEFAULT_EXPENSE_CATEGORIES)
PAYMENT_METHODS = get_dynamic_categories(conn, "expenses", "payment_method", current_user_id, DEFAULT_PAYMENT_METHODS)
INCOME_SOURCES = get_dynamic_categories(conn, "income", "source", current_user_id, DEFAULT_INCOME_SOURCES)

# Sidebar navigation
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
    uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file)
            st.success("Data uploaded successfully!")
            st.write(df.head())
        except Exception as e:
            st.error(f"Error reading file: {e}")
    
    st.markdown("---")
    st.markdown("<p style='text-align: center; color: grey;'>Made with ❤️ by xAI</p>", unsafe_allow_html=True)

# Get current page
current_page = selected_page.split()[1] if selected_page != "🧮 Financial Workbench" else "Financial Workbench"

# Main content area
if current_page == "Dashboard":
    st.title("🏠 Finance Dashboard")
    
    today = datetime.now()
    current_month = today.strftime("%Y-%m")
    last_month = get_last_month()
    
    cols = st.columns(4)
    with cols[0]:
        try:
            monthly_spending = pd.read_sql(
                "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = %s AND DATE_FORMAT(date, '%%Y-%%m') = %s",
                conn, params=(current_user_id, current_month)
            ).iloc[0,0]
            
            last_month_spending = pd.read_sql(
                "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = %s AND DATE_FORMAT(date, '%%Y-%%m') = %s",
                conn, params=(current_user_id, last_month)
            ).iloc[0,0]
            
            change = ((monthly_spending - last_month_spending) / last_month_spending * 100) if last_month_spending else 0
            st.metric("Monthly Spending", f"${monthly_spending:,.2f}", f"{change:.1f}%")
        except Error as e:
            st.error(f"Error loading spending data: {e}")
    
    with cols[1]:
        try:
            monthly_income = pd.read_sql(
                "SELECT COALESCE(SUM(amount), 0) as total FROM income WHERE user_id = %s AND DATE_FORMAT(date, '%%Y-%%m') = %s",
                conn, params=(current_user_id, current_month)
            ).iloc[0,0]
            
            last_month_income = pd.read_sql(
                "SELECT COALESCE(SUM(amount), 0) as total FROM income WHERE user_id = %s AND DATE_FORMAT(date, '%%Y-%%m') = %s",
                conn, params=(current_user_id, last_month)
            ).iloc[0,0]
            
            income_change = ((monthly_income - last_month_income) / last_month_income * 100) if last_month_income else 0
            st.metric("Monthly Income", f"${monthly_income:,.2f}", f"{income_change:.1f}%")
        except Error as e:
            st.error(f"Error loading income data: {e}")
    
    with cols[2]:
        try:
            profit = monthly_income - monthly_spending
            last_month_profit = last_month_income - last_month_spending
            profit_change = ((profit - last_month_profit) / last_month_profit * 100) if last_month_profit else 0
            st.metric("Monthly Profit", f"${profit:,.2f}", f"{profit_change:.1f}%")
        except:
            st.metric("Monthly Profit", "$0.00", "0.0%")
    
    with cols[3]:
        try:
            savings = pd.read_sql(
                "SELECT COALESCE(SUM(current_amount), 0) as saved FROM savings_goals WHERE user_id = %s",
                conn, params=(current_user_id,)
            ).iloc[0,0]
            
            target = pd.read_sql(
                "SELECT COALESCE(SUM(target_amount), 0) as target FROM savings_goals WHERE user_id = %s",
                conn, params=(current_user_id,)
            ).iloc[0,0]
            
            progress = (savings / target * 100) if target else 0
            st.metric("Savings Progress", f"${savings:,.2f}", f"{progress:.1f}% of ${target:,.2f}")
        except Error as e:
            st.error(f"Error loading savings data: {e}")
    
    st.subheader("Financial Health Indicators")
    try:
        ratios = calculate_financial_ratios(conn, current_user_id)
        if ratios:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Savings Rate", f"{ratios['savings_rate']:.1f}%")
            with col2:
                st.metric("Expense Ratio", f"{ratios['expense_ratio']:.1f}%")
            with col3:
                st.metric("Net Worth", f"${ratios['net_worth']:,.2f}")
    except:
        st.warning("Could not calculate financial ratios")
    
    st.subheader("Financial Trends")
    time_period = st.selectbox("Time Period", ["Last 3 Months", "Last 6 Months", "Last 12 Months", "Current Year"])
    
    try:
        date_condition = {
            "Last 3 Months": "date >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH)",
            "Last 6 Months": "date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)",
            "Last 12 Months": "date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)",
            "Current Year": "YEAR(date) = YEAR(CURDATE())"
        }[time_period]
        
        spending_data = pd.read_sql(f"""
            SELECT DATE_FORMAT(date, '%%Y-%%m') as month, 
                   COALESCE(SUM(amount), 0) as spending 
            FROM expenses 
            WHERE user_id = %s AND {date_condition}
            GROUP BY month 
            ORDER BY month
        """, conn, params=(current_user_id,))
        
        income_data = pd.read_sql(f"""
            SELECT DATE_FORMAT(date, '%%Y-%%m') as month, 
                   COALESCE(SUM(amount), 0) as income 
            FROM income 
            WHERE user_id = %s AND {date_condition}
            GROUP BY month 
            ORDER BY month
        """, conn, params=(current_user_id,))
        
        comparison_data = pd.merge(spending_data, income_data, on='month', how='outer').fillna(0)
        comparison_data['profit'] = comparison_data['income'] - comparison_data['spending']
        
        fig = px.bar(
            comparison_data, 
            x='month', 
            y=['income', 'spending', 'profit'], 
            barmode='group',
            title=f"Financial Flow ({time_period})",
            labels={'value': 'Amount ($)', 'month': 'Month'},
            color_discrete_map={
                'income': '#00CC96', 
                'spending': '#EF553B', 
                'profit': '#636EFA'
            }
        )
        st.plotly_chart(fig)
        
    except Error as e:
        st.error(f"Error loading financial trends: {e}")

elif current_page == "Expenses":
    st.title("💸 Expense Tracking")
    
    with st.expander("➕ Add New Expense", expanded=True):
        with st.form("expense_form"):
            amount = st.number_input("Amount ($)", min_value=0.01, step=0.01)
            
            col1, col2 = st.columns(2)
            category = col1.selectbox("Category", EXPENSE_CATEGORIES + ["Add New"])
            if category == "Add New":
                category = col1.text_input("New Category")
            
            subcategory = col2.text_input("Subcategory (Optional)")
            
            col1, col2 = st.columns(2)
            date = col1.date_input("Date", datetime.now())
            payment_method = col2.selectbox("Payment Method", PAYMENT_METHODS + ["Add New"])
            if payment_method == "Add New":
                payment_method = col2.text_input("New Payment Method")
            
            fixed = st.checkbox("Fixed Expense")
            description = st.text_input("Description (Optional)")
            
            submitted = st.form_submit_button("Add Expense")
            if submitted:
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO expenses 
                        (user_id, amount, category, subcategory, date, description, payment_method, fixed) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        current_user_id, amount, category, subcategory, 
                        date.strftime('%Y-%m-%d'), description, payment_method, fixed
                    ))
                    conn.commit()
                    cursor.close()
                    st.success("Expense added successfully!")
                    # Refresh categories
                    EXPENSE_CATEGORIES = get_dynamic_categories(conn, "expenses", "category", current_user_id, DEFAULT_EXPENSE_CATEGORIES)
                    PAYMENT_METHODS = get_dynamic_categories(conn, "expenses", "payment_method", current_user_id, DEFAULT_PAYMENT_METHODS)
                except Error as e:
                    st.error(f"Error adding expense: {e}")
    
    st.subheader("Expense Analysis")
    col1, col2 = st.columns(2)
    start_date = col1.date_input("Start Date", datetime.now() - timedelta(days=30))
    end_date = col2.date_input("End Date", datetime.now())
    
    try:
        expenses_df = pd.read_sql("""
            SELECT date, category, amount, payment_method, description, fixed 
            FROM expenses 
            WHERE user_id = %s AND date BETWEEN %s AND %s 
            ORDER BY date DESC
        """, conn, params=(current_user_id, start_date, end_date))
        
        if not expenses_df.empty:
            total_spent = expenses_df['amount'].sum()
            fixed_expenses = expenses_df[expenses_df['fixed'] == 1]['amount'].sum()
            variable_expenses = total_spent - fixed_expenses
            avg_daily = total_spent / ((end_date - start_date).days + 1)
            
            st.write(f"""
                **Total Spent:** ${total_spent:,.2f} | 
                **Fixed:** ${fixed_expenses:,.2f} | 
                **Variable:** ${variable_expenses:,.2f} | 
                **Avg Daily:** ${avg_daily:,.2f}
            """)
            
            st.dataframe(expenses_df)
            
            tab1, tab2, tab3 = st.tabs(["By Category", "By Payment Method", "Fixed vs Variable"])
            
            with tab1:
                cat_data = expenses_df.groupby('category')['amount'].sum().reset_index()
                fig = px.pie(cat_data, values='amount', names='category', title="Expense Distribution by Category")
                st.plotly_chart(fig)
            
            with tab2:
                pm_data = expenses_df.groupby('payment_method')['amount'].sum().reset_index()
                fig = px.bar(pm_data, x='payment_method', y='amount', title="Expenses by Payment Method")
                st.plotly_chart(fig)
            
            with tab3:
                fv_data = expenses_df.groupby('fixed')['amount'].sum().reset_index()
                fv_data['type'] = fv_data['fixed'].apply(lambda x: 'Fixed' if x == 1 else 'Variable')
                fig = px.pie(fv_data, values='amount', names='type', title="Fixed vs Variable Expenses")
                st.plotly_chart(fig)
        else:
            st.info("No expenses found for the selected period")
    
    except Error as e:
        st.error(f"Error loading expenses: {e}")

elif current_page == "Income":
    st.title("💵 Income Tracking")
    
    with st.expander("➕ Add New Income", expanded=True):
        with st.form("income_form"):
            amount = st.number_input("Amount ($)", min_value=0.01, step=0.01)
            
            col1, col2 = st.columns(2)
            source = col1.selectbox("Source", INCOME_SOURCES + ["Add New"])
            if source == "Add New":
                source = col1.text_input("New Source")
            
            date = col2.date_input("Date", datetime.now())
            
            fixed = st.checkbox("Fixed Income")
            description = st.text_input("Description (Optional)")
            
            submitted = st.form_submit_button("Add Income")
            if submitted:
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO income 
                        (user_id, amount, source, date, description, fixed) 
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        current_user_id, amount, source, 
                        date.strftime('%Y-%m-%d'), description, fixed
                    ))
                    conn.commit()
                    cursor.close()
                    st.success("Income added successfully!")
                    INCOME_SOURCES = get_dynamic_categories(conn, "income", "source", current_user_id, DEFAULT_INCOME_SOURCES)
                except Error as e:
                    st.error(f"Error adding income: {e}")
    
    st.subheader("Income Analysis")
    col1, col2 = st.columns(2)
    start_date = col1.date_input("Start Date", datetime.now() - timedelta(days=30))
    end_date = col2.date_input("End Date", datetime.now())
    
    try:
        income_df = pd.read_sql("""
            SELECT date, source, amount, description, fixed 
            FROM income 
            WHERE user_id = %s AND date BETWEEN %s AND %s 
            ORDER BY date DESC
        """, conn, params=(current_user_id, start_date, end_date))
        
        if not income_df.empty:
            total_income = income_df['amount'].sum()
            fixed_income = income_df[income_df['fixed'] == 1]['amount'].sum()
            variable_income = total_income - fixed_income
            avg_daily = total_income / ((end_date - start_date).days + 1)
            
            st.write(f"""
                **Total Income:** ${total_income:,.2f} | 
                **Fixed:** ${fixed_income:,.2f} | 
                **Variable:** ${variable_income:,.2f} | 
                **Avg Daily:** ${avg_daily:,.2f}
            """)
            
            st.dataframe(income_df)
            
            tab1, tab2 = st.tabs(["By Source", "Fixed vs Variable"])
            
            with tab1:
                source_data = income_df.groupby('source')['amount'].sum().reset_index()
                fig = px.bar(source_data, x='source', y='amount', title="Income by Source")
                st.plotly_chart(fig)
            
            with tab2:
                fv_data = income_df.groupby('fixed')['amount'].sum().reset_index()
                fv_data['type'] = fv_data['fixed'].apply(lambda x: 'Fixed' if x == 1 else 'Variable')
                fig = px.pie(fv_data, values='amount', names='type', title="Fixed vs Variable Income")
                st.plotly_chart(fig)
        else:
            st.info("No income found for the selected period")
    
    except Error as e:
        st.error(f"Error loading income: {e}")

elif current_page == "Budgets":
    st.title("📊 Budget Management")
    
    with st.expander("➕ Add New Budget", expanded=True):
        with st.form("budget_form"):
            col1, col2 = st.columns(2)
            category = col1.selectbox("Category", EXPENSE_CATEGORIES + ["Add New"])
            if category == "Add New":
                category = col1.text_input("New Category")
            
            subcategory = col2.text_input("Subcategory (Optional)")
            
            col1, col2 = st.columns(2)
            limit_amount = col1.number_input("Limit Amount ($)", min_value=0.01, step=0.01)
            period = col2.selectbox("Period", PERIOD_OPTIONS)
            
            submitted = st.form_submit_button("Add Budget")
            if submitted:
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO budgets 
                        (user_id, category, subcategory, limit_amount, period) 
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        current_user_id, category, subcategory, limit_amount, period
                    ))
                    conn.commit()
                    cursor.close()
                    st.success("Budget added successfully!")
                except Error as e:
                    st.error(f"Error adding budget: {e}")
    
    st.subheader("Budget Status")
    try:
        budgets_df = pd.read_sql(
            "SELECT category, subcategory, limit_amount, period FROM budgets WHERE user_id = %s",
            conn, params=(current_user_id,)
        )
        
        if not budgets_df.empty:
            current_month = datetime.now().strftime("%Y-%m")
            budget_status = []
            
            for _, budget in budgets_df.iterrows():
                spending = pd.read_sql(
                    "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = %s AND category = %s AND DATE_FORMAT(date, '%%Y-%%m') = %s",
                    conn, params=(current_user_id, budget['category'], current_month)
                ).iloc[0,0]
                
                budget_status.append({
                    'Category': budget['category'],
                    'Subcategory': budget['subcategory'],
                    'Limit': budget['limit_amount'],
                    'Spent': spending,
                    'Remaining': budget['limit_amount'] - spending,
                    'Period': budget['period']
                })
            
            status_df = pd.DataFrame(budget_status)
            st.dataframe(status_df)
            
            fig = px.bar(
                status_df, 
                x='Category', 
                y=['Limit', 'Spent', 'Remaining'], 
                barmode='group',
                title="Budget Status"
            )
            st.plotly_chart(fig)
        else:
            st.info("No budgets set")
    
    except Error as e:
        st.error(f"Error loading budgets: {e}")

elif current_page == "Goals":
    st.title("🎯 Savings Goals")
    
    with st.expander("➕ Add New Goal", expanded=True):
        with st.form("goal_form"):
            goal_name = st.text_input("Goal Name")
            
            col1, col2 = st.columns(2)
            target_amount = col1.number_input("Target Amount ($)", min_value=0.01, step=0.01)
            current_amount = col2.number_input("Current Amount ($)", min_value=0.00, step=0.01)
            
            col1, col2 = st.columns(2)
            target_date = col1.date_input("Target Date", datetime.now() + timedelta(days=365))
            priority = col2.number_input("Priority (1-10)", min_value=1, max_value=10, step=1)
            
            risk_tolerance = st.selectbox("Risk Tolerance", RISK_TOLERANCE_OPTIONS)
            description = st.text_area("Description (Optional)")
            
            submitted = st.form_submit_button("Add Goal")
            if submitted:
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO savings_goals 
                        (user_id, goal_name, target_amount, current_amount, target_date, priority, description, risk_tolerance) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        current_user_id, goal_name, target_amount, current_amount,
                        target_date.strftime('%Y-%m-%d'), priority, description, risk_tolerance
                    ))
                    conn.commit()
                    cursor.close()
                    st.success("Goal added successfully!")
                except Error as e:
                    st.error(f"Error adding goal: {e}")
    
    st.subheader("Goal Progress")
    try:
        goals_df = pd.read_sql(
            "SELECT goal_name, target_amount, current_amount, target_date, priority, risk_tolerance FROM savings_goals WHERE user_id = %s",
            conn, params=(current_user_id,)
        )
        
        if not goals_df.empty:
            goals_df['Progress'] = (goals_df['current_amount'] / goals_df['target_amount'] * 100).round(2)
            st.dataframe(goals_df)
            
            fig = px.bar(
                goals_df, 
                x='goal_name', 
                y=['target_amount', 'current_amount'], 
                barmode='group',
                title="Savings Goal Progress"
            )
            st.plotly_chart(fig)
        else:
            st.info("No savings goals set")
    
    except Error as e:
        st.error(f"Error loading goals: {e}")

elif current_page == "Analytics":
    st.title("📈 Financial Analytics")
    
    st.subheader("Cash Flow Analysis")
    time_period = st.selectbox("Time Period", ["Last 3 Months", "Last 6 Months", "Last 12 Months", "Current Year"])
    
    try:
        date_condition = {
            "Last 3 Months": "date >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH)",
            "Last 6 Months": "date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)",
            "Last 12 Months": "date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)",
            "Current Year": "YEAR(date) = YEAR(CURDATE())"
        }[time_period]
        
        cash_flow = pd.read_sql(f"""
            SELECT DATE_FORMAT(date, '%%Y-%%m') as month, 
                   COALESCE(SUM(CASE WHEN type='Income' THEN amount ELSE -amount END), 0) as net_cash
            FROM (
                SELECT date, amount, 'Expense' as type FROM expenses WHERE user_id = %s AND {date_condition}
                UNION ALL
                SELECT date, amount, 'Income' as type FROM income WHERE user_id = %s AND {date_condition}
            ) combined
            GROUP BY month
            ORDER BY month
        """, conn, params=(current_user_id, current_user_id))
        
        if not cash_flow.empty:
            fig = px.line(
                cash_flow, 
                x='month', 
                y='net_cash', 
                title="Net Cash Flow Over Time",
                labels={'net_cash': 'Net Cash ($)', 'month': 'Month'}
            )
            st.plotly_chart(fig)
        else:
            st.info("No cash flow data available")
    
    except Error as e:
        st.error(f"Error loading cash flow: {e}")

elif current_page == "Reports":
    st.title("📑 Financial Reports")
    
    st.subheader("Generate Report")
    report_type = st.selectbox("Report Type", ["Summary", "Detailed"])
    start_date = st.date_input("Start Date", datetime.now() - timedelta(days=30))
    end_date = st.date_input("End Date", datetime.now())
    
    if st.button("Generate PDF Report"):
        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            
            pdf.cell(200, 10, txt="Financial Report", ln=True, align='C')
            pdf.cell(200, 10, txt=f"Period: {start_date} to {end_date}", ln=True, align='C')
            
            # Summary data
            expenses = pd.read_sql(
                "SELECT category, SUM(amount) as total FROM expenses WHERE user_id = %s AND date BETWEEN %s AND %s GROUP BY category",
                conn, params=(current_user_id, start_date, end_date)
            )
            income = pd.read_sql(
                "SELECT source, SUM(amount) as total FROM income WHERE user_id = %s AND date BETWEEN %s AND %s GROUP BY source",
                conn, params=(current_user_id, start_date, end_date)
            )
            
            pdf.ln(10)
            pdf.cell(200, 10, txt="Income Summary", ln=True)
            for _, row in income.iterrows():
                pdf.cell(200, 10, txt=f"{row['source']}: ${row['total']:,.2f}", ln=True)
            
            pdf.ln(10)
            pdf.cell(200, 10, txt="Expense Summary", ln=True)
            for _, row in expenses.iterrows():
                pdf.cell(200, 10, txt=f"{row['category']}: ${row['total']:,.2f}", ln=True)
            
            pdf_file = "financial_report.pdf"
            pdf.output(pdf_file)
            
            with open(pdf_file, "rb") as f:
                st.download_button(
                    label="Download Report",
                    data=f,
                    file_name=pdf_file,
                    mime="application/pdf"
                )
            
            os.remove(pdf_file)
            
        except Error as e:
            st.error(f"Error generating report: {e}")

elif current_page == "Investments":
    st.title("💰 Investment Tracking")
    
    with st.expander("➕ Add New Investment", expanded=True):
        with st.form("investment_form"):
            asset_name = st.text_input("Asset Name")
            
            col1, col2 = st.columns(2)
            amount_invested = col1.number_input("Amount Invested ($)", min_value=0.01, step=0.01)
            current_value = col2.number_input("Current Value ($)", min_value=0.01, step=0.01)
            
            col1, col2 = st.columns(2)
            purchase_date = col1.date_input("Purchase Date", datetime.now())
            asset_type = col2.selectbox("Asset Type", ASSET_TYPES)
            
            col1, col2 = st.columns(2)
            risk_level = col1.selectbox("Risk Level", RISK_TOLERANCE_OPTIONS)
            expected_return = col2.number_input("Expected Return (%)", min_value=0.0, step=0.01)
            
            submitted = st.form_submit_button("Add Investment")
            if submitted:
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO investments 
                        (user_id, asset_name, amount_invested, current_value, purchase_date, asset_type, risk_level, expected_return) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        current_user_id, asset_name, amount_invested, current_value,
                        purchase_date.strftime('%Y-%m-%d'), asset_type, risk_level, expected_return
                    ))
                    conn.commit()
                    cursor.close()
                    st.success("Investment added successfully!")
                except Error as e:
                    st.error(f"Error adding investment: {e}")
    
    st.subheader("Investment Portfolio")
    try:
        investments_df = pd.read_sql(
            "SELECT asset_name, amount_invested, current_value, purchase_date, asset_type, risk_level, expected_return FROM investments WHERE user_id = %s",
            conn, params=(current_user_id,)
        )
        
        if not investments_df.empty:
            investments_df['ROI'] = ((investments_df['current_value'] - investments_df['amount_invested']) / investments_df['amount_invested'] * 100).round(2)
            st.dataframe(investments_df)
            
            fig = px.pie(
                investments_df, 
                values='current_value', 
                names='asset_type', 
                title="Portfolio Allocation by Asset Type"
            )
            st.plotly_chart(fig)
        else:
            st.info("No investments recorded")
    
    except Error as e:
        st.error(f"Error loading investments: {e}")

elif current_page == "Recurring":
    st.title("🔄 Recurring Transactions")
    
    with st.expander("➕ Add New Recurring Transaction", expanded=True):
        with st.form("recurring_form"):
            col1, col2 = st.columns(2)
            type = col1.selectbox("Type", ["Income", "Expense"])
            amount = col2.number_input("Amount ($)", min_value=0.01, step=0.01)
            
            col1, col2 = st.columns(2)
            category = col1.selectbox("Category", EXPENSE_CATEGORIES if type == "Expense" else INCOME_SOURCES)
            frequency = col2.selectbox("Frequency", FREQUENCY_OPTIONS)
            
            next_date = st.date_input("Next Date", datetime.now())
            
            submitted = st.form_submit_button("Add Recurring Transaction")
            if submitted:
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO recurring 
                        (user_id, type, amount, category, frequency, next_date) 
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        current_user_id, type, amount, category, frequency,
                        next_date.strftime('%Y-%m-%d')
                    ))
                    conn.commit()
                    cursor.close()
                    st.success("Recurring transaction added successfully!")
                except Error as e:
                    st.error(f"Error adding recurring transaction: {e}")
    
    st.subheader("Recurring Transactions")
    try:
        recurring_df = pd.read_sql(
            "SELECT type, amount, category, frequency, next_date FROM recurring WHERE user_id = %s",
            conn, params=(current_user_id,)
        )
        
        if not recurring_df.empty:
            st.dataframe(recurring_df)
        else:
            st.info("No recurring transactions set")
    
    except Error as e:
        st.error(f"Error loading recurring transactions: {e}")

elif current_page == "Financial Workbench":
    st.title("🧮 Financial Workbench")
    
    st.subheader("Portfolio Optimization")
    try:
        investments = pd.read_sql(
            "SELECT asset_name, current_value, expected_return, risk_level FROM investments WHERE user_id = %s",
            conn, params=(current_user_id,)
        )
        
        if not investments.empty:
            # Simple optimization example
            def objective(weights, returns):
                return -np.sum(returns * weights)
            
            constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
            bounds = tuple((0, 1) for _ in range(len(investments)))
            initial_guess = [1./len(investments)] * len(investments)
            
            result = minimize(
                objective,
                initial_guess,
                args=(investments['expected_return'],),
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
                
                fig = px.pie(
                    allocation, 
                    values='Optimal Weight', 
                    names='Asset', 
                    title="Optimized Portfolio Allocation"
                )
                st.plotly_chart(fig)
            else:
                st.warning("Optimization failed")
        else:
            st.info("No investments available for optimization")
    
    except Error as e:
        st.error(f"Error optimizing portfolio: {e}")