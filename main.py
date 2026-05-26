import os
import requests
import psycopg2
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
SISTER_USERNAME = os.getenv("SISTER_USERNAME")
SISTER_PASSWORD = os.getenv("SISTER_PASSWORD")
SISTER_ID_PENGGUNA = os.getenv("SISTER_ID_PENGGUNA")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

BASE_URL = "https://sister-api.kemdiktisaintek.go.id/ws.php/1.0"
TARGET_SEMESTERS = [20251, 20242, 20241]

def create_db_connection():
    """Establish connection to PostgreSQL."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return None

def init_db(conn):
    """Initialize the database table."""
    create_table_query = """
    CREATE TABLE IF NOT EXISTS bkd_penelitian (
        id SERIAL PRIMARY KEY,
        nm_sdm VARCHAR(255),
        nidn BIGINT,
        id_smt INTEGER,
        unsur VARCHAR(255),
        judul_keg TEXT,
        id_katgiat INTEGER,
        nm_kat VARCHAR(255),
        beban_sks NUMERIC,
        nilai NUMERIC
    );
    """
    try:
        with conn.cursor() as cur:
            cur.execute(create_table_query)
            conn.commit()
            print("Table 'bkd_penelitian' is ready.")
    except Exception as e:
        print(f"Error initializing database: {e}")

def get_auth_token():
    """Authenticate and retrieve JWT token from SISTER API."""
    url = f"{BASE_URL}/authorize"
    payload = {
        "username": SISTER_USERNAME,
        "password": SISTER_PASSWORD,
        "id_pengguna": SISTER_ID_PENGGUNA
    }
    
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        data = response.json()
        # The token is usually in 'token' or inside a 'data' object depending on the response format
        token = data.get("token") or (data.get("data", {}).get("token") if isinstance(data.get("data"), dict) else None)
        if token:
            print("Successfully authenticated.")
            return token
        else:
            print(f"Authentication succeeded but couldn't find token in response: {data}")
            return None
    else:
        print(f"Authentication failed with status {response.status_code}: {response.text}")
        return None

def fetch_sdm_list(token):
    """Fetch the list of SDM from the API to get id_sdm."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}/referensi/sdm"
    
    print("Fetching SDM list...")
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        # Assuming the data is returned as a list or within a 'data' key
        data = response.json()
        sdm_list = data if isinstance(data, list) else data.get("data", [])
        print(f"Fetched {len(sdm_list)} SDM records.")
        return sdm_list
    else:
        print(f"Failed to fetch SDM list: {response.text}")
        return []

def fetch_penelitian_data(token, id_sdm, id_smt):
    """Fetch BKD Penelitian data for a specific SDM and Semester."""
    headers = {"Authorization": f"Bearer {token}"}
    
    # Adjusting URL based on typical SISTER API patterns. 
    # Try passing them as query params first. If it uses path params instead, uncomment the line below.
    # url = f"{BASE_URL}/bkd/penelitian/{id_sdm}/{id_smt}"
    url = f"{BASE_URL}/bkd/penelitian"
    params = {
        "id_sdm": id_sdm,
        "id_smt": id_smt
    }
    
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        return data if isinstance(data, list) else data.get("data", [])
    else:
        print(f"Failed to fetch data for SDM {id_sdm}, SMT {id_smt}: {response.text}")
        return []

def insert_data(conn, records):
    """Insert fetched records into the database."""
    if not records:
        return
        
    insert_query = """
    INSERT INTO bkd_penelitian (nm_sdm, nidn, id_smt, unsur, judul_keg, id_katgiat, nm_kat, beban_sks, nilai)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    try:
        with conn.cursor() as cur:
            for record in records:
                cur.execute(insert_query, (
                    record.get("nm_sdm"),
                    record.get("nidn"),
                    record.get("id_smt"),
                    record.get("unsur"),
                    record.get("judul_keg"),
                    record.get("id_katgiat"),
                    record.get("nm_kat"),
                    record.get("beban_sks"),
                    record.get("nilai")
                ))
            conn.commit()
            print(f"Successfully inserted {len(records)} records.")
    except Exception as e:
        print(f"Error inserting data: {e}")
        conn.rollback()

def main():
    # 1. Connect to DB and Initialize Table
    conn = create_db_connection()
    if not conn:
        return
    init_db(conn)

    # 2. Get API Token
    token = get_auth_token()
    if not token:
        conn.close()
        return

    # 3. Get SDM List
    sdm_list = fetch_sdm_list(token)
    
    # 4. Loop through each SDM and target semesters to fetch and insert data
    for sdm in sdm_list:
        # Check field name depending on actual API response (might be 'id_sdm' or 'id')
        id_sdm = sdm.get("id_sdm") or sdm.get("id") 
        if not id_sdm:
            continue
            
        print(f"\nProcessing SDM: {id_sdm} - {sdm.get('nm_sdm', 'Unknown')}")
        
        for id_smt in TARGET_SEMESTERS:
            print(f"  Fetching SMT: {id_smt}...")
            penelitian_records = fetch_penelitian_data(token, id_sdm, id_smt)
            
            if penelitian_records:
                insert_data(conn, penelitian_records)
            else:
                print("  No records found or error occurred.")

    # Close DB connection
    conn.close()
    print("\nData Extraction Process Finished!")

if __name__ == "__main__":
    main()
