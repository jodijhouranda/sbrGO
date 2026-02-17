import os
import pymysql
import toml

def migrate():
    # Load secrets
    secrets_path = os.path.join(".streamlit", "secrets.toml")
    if not os.path.exists(secrets_path):
        print("Secrets not found!")
        return
    
    config = toml.load(secrets_path)
    db_config = config['connections']['tidb']
    
    # Connection details
    user = db_config['username']
    pw = db_config['password']
    host = db_config['host']
    port = db_config['port']
    db = db_config['database']
    # Resolve SSL CA path relative to the app root
    ssl_ca = os.path.abspath(db_config.get('ssl_ca', 'isrgrootx1.pem'))

    print(f"Connecting to {host}...")
    
    connection = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=pw,
        database=db,
        ssl={'ca': ssl_ca}
    )

    try:
        with connection.cursor() as cursor:
            # 1. Create users table
            print("Creating users table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username VARCHAR(255) PRIMARY KEY,
                    password VARCHAR(255) NOT NULL,
                    is_superuser BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 2. Add username column to scraped_results
            print("Checking scraped_results columns...")
            cursor.execute("DESCRIBE scraped_results")
            columns = [col[0] for col in cursor.fetchall()]
            
            if 'username' not in columns:
                print("Adding username column to scraped_results...")
                cursor.execute("ALTER TABLE scraped_results ADD COLUMN username VARCHAR(255) DEFAULT 'system'")
            else:
                print("Username column already exists.")
            
            # 3. Create default superuser 'jodi'
            print("Checking if user 'jodi' exists...")
            cursor.execute("SELECT * FROM users WHERE username = 'jodi'")
            if not cursor.fetchone():
                print("Creating superuser 'jodi'...")
                cursor.execute("INSERT INTO users (username, password, is_superuser) VALUES ('jodi', 'jodi', TRUE)")
            else:
                print("User 'jodi' already exists.")
                
        connection.commit()
        print("Migration successful!")
        
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        connection.close()

if __name__ == "__main__":
    migrate()
