import psycopg2
from psycopg2.extras import execute_batch, Json
from datetime import datetime, timedelta
import sys

print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting sync to cloud...")

try:
    # Connect to LOCAL PostgreSQL
    print("Connecting to local database...")
    local_conn = psycopg2.connect(
        host="localhost",
        database="trading_data",
        user="postgres",
        password="Trading321",
        port=5432
    )
    print("✓ Local connection established")

    # Connect to CLOUD PostgreSQL
    print("Connecting to cloud database...")
    cloud_conn = psycopg2.connect(
        host="145.241.242.224",
        database="trading_data",
        user="postgres",
        password="Trading_321",
        port=5432
    )
    print("✓ Cloud connection established")

    # Get the latest timestamp from cloud
    cloud_cursor = cloud_conn.cursor()
    cloud_cursor.execute("SELECT MAX(created_at) FROM numeric_data")
    last_sync = cloud_cursor.fetchone()[0]

    if last_sync is None:
        # First sync - get last 24 hours
        last_sync = datetime.now() - timedelta(hours=24)
        print(f"First sync - will sync last 24 hours of data")
    else:
        print(f"Last cloud sync: {last_sync}")

    # Get new records from local
    local_cursor = local_conn.cursor()
    local_cursor.execute("""
        SELECT timestamp, source, category, symbol, data_type, 
               numeric_value, metadata, created_at
        FROM numeric_data
        WHERE created_at > %s
        ORDER BY created_at
    """, (last_sync,))

    new_records = local_cursor.fetchall()

    if len(new_records) == 0:
        print("✓ No new records to sync - database is current")
    else:
        print(f"Found {len(new_records):,} new records to sync...")
        
        # Convert metadata to Json objects
        converted_records = []
        for record in new_records:
            record_list = list(record)
            if record_list[6]:  # metadata field
                record_list[6] = Json(record_list[6])
            converted_records.append(tuple(record_list))
        
        # Insert into cloud (batch processing)
        insert_query = """
            INSERT INTO numeric_data 
            (timestamp, source, category, symbol, data_type, numeric_value, metadata, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """
        
        batch_size = 5000
        total_synced = 0
        
        for i in range(0, len(converted_records), batch_size):
            batch = converted_records[i:i + batch_size]
            execute_batch(cloud_cursor, insert_query, batch, page_size=1000)
            cloud_conn.commit()
            total_synced += len(batch)
            print(f"  Synced {total_synced:,} / {len(new_records):,} records...")
        
        print(f"✅ Successfully synced {total_synced:,} records to cloud")

    # Cleanup
    local_cursor.close()
    cloud_cursor.close()
    local_conn.close()
    cloud_conn.close()

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Sync completed successfully!")
    sys.exit(0)

except Exception as e:
    print(f"❌ ERROR: {e}")
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Sync failed!")
    sys.exit(1)




## **SAVE THE FILE**

#**File location should be:**

#C:\Users\Digital Technologies\Quant_Folder 2\data_gathering\sync_to_cloud.py