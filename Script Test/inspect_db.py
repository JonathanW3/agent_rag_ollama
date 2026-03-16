import sqlite3
import sys

db_path = r"c:\Proyectos\rag_ollama_api\mcp_sqlite\schemas\monitoring.db"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Obtener todas las tablas
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()
    
    print(f"\n🔍 BASE DE DATOS: monitoring.db")
    print(f"📍 Ruta: {db_path}")
    print(f"📊 Total de tablas: {len(tables)}\n")
    
    if not tables:
        print("⚠️  La base de datos no tiene tablas creadas.\n")
    else:
        print("=" * 60)
        print("TABLAS ENCONTRADAS:")
        print("=" * 60)
        
        for idx, (table_name,) in enumerate(tables, 1):
            print(f"\n{idx}. 📋 {table_name}")
            
            # Obtener información de las columnas
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            
            print(f"   Columnas ({len(columns)}):")
            for col in columns:
                col_id, col_name, col_type, not_null, default_val, pk = col
                pk_text = " [PK]" if pk else ""
                null_text = " NOT NULL" if not_null else ""
                print(f"   - {col_name} ({col_type}){pk_text}{null_text}")
            
            # Obtener cantidad de registros
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            print(f"   📈 Registros: {count}")
    
    print("\n" + "=" * 60 + "\n")
    conn.close()
    
except sqlite3.Error as e:
    print(f"❌ Error al conectar a la base de datos: {e}")
    sys.exit(1)
except FileNotFoundError:
    print(f"❌ No se encontró el archivo: {db_path}")
    sys.exit(1)
