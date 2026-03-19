
import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import time

st.set_page_config(page_title="Trading Data System", layout="wide")

# PostgreSQL connection
def get_connection():
    return psycopg2.connect(
        host="localhost",
        database="trading_data",
        user="postgres",
        password="Trading321"
    )

st.title("Real-Time Trading Data Collection System")

placeholder = st.empty()

while True:
    with placeholder.container():
        
        col1, col2, col3, col4 = st.columns(4)
        
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM numeric_data")
        total = cursor.fetchone()[0]
        
        now = datetime.now()
        hot_cutoff = now - timedelta(hours=1)
        cursor.execute("SELECT COUNT(*) FROM numeric_data WHERE timestamp >= %s", (hot_cutoff,))
        hot = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT source) FROM numeric_data")
        sources = cursor.fetchone()[0]
        
        with col1:
            st.metric("Total Records", f"{total:,}")
        with col2:
            st.metric("HOT (Last 1h)", f"{hot:,}")
        with col3:
            st.metric("Active Sources", sources)
        with col4:
            st.metric("WARM", f"{total - hot:,}")
        
        st.subheader("Latest Prices")
        prices_df = pd.read_sql_query("""
            SELECT DISTINCT ON (source, symbol) 
                source, symbol, numeric_value as price, timestamp
            FROM numeric_data
            WHERE data_type = 'price'
            ORDER BY source, symbol, timestamp DESC
            LIMIT 20
        """, conn)
        st.dataframe(prices_df, use_container_width=True)
        
        st.subheader("Latest Headlines")
        news_df = pd.read_sql_query("""
            SELECT source, timestamp, metadata
            FROM numeric_data
            WHERE data_type = 'headline'
            ORDER BY timestamp DESC
            LIMIT 10
        """, conn)
        
        if not news_df.empty:
            for _, row in news_df.iterrows():
                import json
                meta = json.loads(row['metadata']) if isinstance(row['metadata'], str) else row['metadata']
                st.write(f"**{row['source']}** - {meta.get('title', 'No title')}")
        
        st.subheader("Records by Source")
        source_df = pd.read_sql_query("""
            SELECT source, COUNT(*) as count
            FROM numeric_data
            GROUP BY source
            ORDER BY count DESC
        """, conn)
        st.bar_chart(source_df.set_index('source'))
        
        conn.close()
        
        st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
    
    time.sleep(2)
