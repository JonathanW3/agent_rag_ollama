import sqlite3
from datetime import datetime

db_path = r"c:\Proyectos\rag_ollama_api\mcp_sqlite\schemas\monitoring.db"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=" * 80)
    print("🔍 VERIFICANDO NOMBRES DE SERVIDORES")
    print("=" * 80)
    
    # Primero, ver todos los nombres de servidores disponibles
    cursor.execute("""
        SELECT DISTINCT nombre, ip 
        FROM servers 
        WHERE nombre LIKE '%Multiplaza%' OR nombre LIKE '%multiplaza%'
        ORDER BY nombre
    """)
    servers = cursor.fetchall()
    
    if servers:
        print("\n📋 Servidores encontrados con 'Multiplaza':")
        for nombre, ip in servers:
            print(f"   • {nombre} — {ip}")
    else:
        print("\n⚠️  No se encontró 'Multiplaza' en la tabla servers")
        print("\n📋 Listando todos los servidores disponibles:")
        cursor.execute("SELECT nombre, ip FROM servers ORDER BY nombre LIMIT 10")
        all_servers = cursor.fetchall()
        for nombre, ip in all_servers:
            print(f"   • {nombre} — {ip}")
    
    print("\n" + "=" * 80)
    print("📊 ANÁLISIS DE MONITOREO - ÚLTIMOS 7 DÍAS")
    print("=" * 80)
    
    # Ejecutar la query de monitoreo para Multiplaza
    cursor.execute("""
        SELECT 
            server_nombre,
            COUNT(*) as total_checks,
            SUM(exitosas) as total_exitosas,
            SUM(fallidas) as total_fallidas,
            ROUND(AVG(exitosas * 100.0 / NULLIF(total_consultas, 0)), 2) as tasa_exito,
            MAX(timestamp) as ultimo_check,
            MIN(timestamp) as primer_check
        FROM monitoring_results
        WHERE (server_nombre LIKE '%Multiplaza%' OR server_nombre LIKE '%multiplaza%')
          AND timestamp >= datetime('now', '-7 days')
        GROUP BY server_nombre
    """)
    
    results = cursor.fetchall()
    
    if results:
        print("\n🏢 Servidor: Multiplaza\n")
        for row in results:
            server, checks, exitosas, fallidas, tasa, ultimo, primero = row
            
            # Calcular estado
            if tasa >= 95:
                estado = "✅ Saludable"
            elif tasa >= 85:
                estado = "⚠️ Atención"
            else:
                estado = "🔴 Crítico"
            
            print(f"📍 Servidor: {server}")
            print(f"🔍 Total Checks: {checks}")
            print(f"✅ Exitosas: {exitosas} ({tasa}%)")
            print(f"❌ Fallidas: {fallidas}")
            print(f"📈 Tasa de Éxito: {tasa}%")
            print(f"⏱️ Último Check: {ultimo}")
            print(f"🎯 Estado: {estado}")
            print(f"\n📅 Período analizado: {primero} → {ultimo}")
            
            # Detalles adicionales por día
            print(f"\n📊 DESGLOSE POR DÍA:")
            print("-" * 80)
            
            cursor.execute("""
                SELECT 
                    DATE(timestamp) as fecha,
                    COUNT(*) as checks,
                    SUM(exitosas) as exitosas,
                    SUM(fallidas) as fallidas,
                    ROUND(AVG(exitosas * 100.0 / NULLIF(total_consultas, 0)), 2) as tasa
                FROM monitoring_results
                WHERE (server_nombre LIKE '%Multiplaza%' OR server_nombre LIKE '%multiplaza%')
                  AND timestamp >= datetime('now', '-7 days')
                GROUP BY DATE(timestamp)
                ORDER BY fecha DESC
            """)
            
            daily = cursor.fetchall()
            print(f"{'Fecha':<12} {'Checks':<8} {'✅ Éxito':<10} {'❌ Fallos':<10} {'Tasa':<8} {'Estado'}")
            print("-" * 80)
            
            for fecha, chk, ex, fll, ts in daily:
                estado_dia = "✅" if ts >= 95 else "⚠️" if ts >= 85 else "🔴"
                print(f"{fecha:<12} {chk:<8} {ex:<10} {fll:<10} {ts}%{' '*(7-len(str(ts)))} {estado_dia}")
            
            # Distribución por hora
            print(f"\n📈 DISTRIBUCIÓN POR HORA (últimas 24h):")
            print("-" * 80)
            
            cursor.execute("""
                SELECT 
                    strftime('%H', timestamp) as hora,
                    COUNT(*) as checks,
                    SUM(exitosas) as exitosas,
                    SUM(fallidas) as fallidas,
                    ROUND(AVG(exitosas * 100.0 / NULLIF(total_consultas, 0)), 2) as tasa
                FROM monitoring_results
                WHERE (server_nombre LIKE '%Multiplaza%' OR server_nombre LIKE '%multiplaza%')
                  AND timestamp >= datetime('now', '-24 hours')
                GROUP BY strftime('%H', timestamp)
                ORDER BY hora DESC
                LIMIT 10
            """)
            
            hourly = cursor.fetchall()
            if hourly:
                print(f"{'Hora':<6} {'Checks':<8} {'✅ Éxito':<10} {'❌ Fallos':<10} {'Tasa'}")
                print("-" * 60)
                for hora, chk, ex, fll, ts in hourly:
                    print(f"{hora}:00{' ':<2} {chk:<8} {ex:<10} {fll:<10} {ts}%")
            else:
                print("   No hay datos de las últimas 24 horas")
            
    else:
        print("\n⚠️  No se encontraron resultados de monitoreo para Multiplaza en los últimos 7 días")
        
        # Mostrar servidores con datos recientes
        print("\n📋 Servidores con datos recientes (últimos 7 días):")
        cursor.execute("""
            SELECT DISTINCT server_nombre, COUNT(*) as checks
            FROM monitoring_results
            WHERE timestamp >= datetime('now', '-7 days')
            GROUP BY server_nombre
            ORDER BY checks DESC
            LIMIT 10
        """)
        recent = cursor.fetchall()
        for srv, cnt in recent:
            print(f"   • {srv} — {cnt} checks")
    
    # Comparativa con semana anterior
    print("\n" + "=" * 80)
    print("📊 COMPARATIVA: ESTA SEMANA vs SEMANA ANTERIOR")
    print("=" * 80)
    
    cursor.execute("""
        SELECT 
            CASE 
                WHEN timestamp >= datetime('now', '-7 days') THEN 'Esta semana'
                ELSE 'Semana anterior'
            END as periodo,
            COUNT(*) as checks,
            SUM(exitosas) as exitosas,
            SUM(fallidas) as fallidas,
            ROUND(AVG(exitosas * 100.0 / NULLIF(total_consultas, 0)), 2) as tasa_exito
        FROM monitoring_results
        WHERE (server_nombre LIKE '%Multiplaza%' OR server_nombre LIKE '%multiplaza%')
          AND timestamp >= datetime('now', '-14 days')
        GROUP BY periodo
        ORDER BY periodo DESC
    """)
    
    comparison = cursor.fetchall()
    
    if comparison:
        print(f"\n{'Período':<20} {'Checks':<10} {'✅ Éxito':<12} {'❌ Fallos':<12} {'Tasa'}")
        print("-" * 80)
        
        for periodo, chk, ex, fll, ts in comparison:
            print(f"{periodo:<20} {chk:<10} {ex:<12} {fll:<12} {ts}%")
        
        if len(comparison) == 2:
            esta = comparison[0]
            anterior = comparison[1]
            
            diff_checks = esta[1] - anterior[1]
            diff_tasa = esta[4] - anterior[4]
            
            print(f"\n📈 CAMBIOS:")
            print(f"   Checks: {'+' if diff_checks > 0 else ''}{diff_checks}")
            print(f"   Tasa Éxito: {'+' if diff_tasa > 0 else ''}{diff_tasa:.2f}%")
            
            if diff_tasa > 0:
                print(f"   🎯 Tendencia: ⬆️ Mejorando")
            elif diff_tasa < 0:
                print(f"   🎯 Tendencia: ⬇️ Deteriorando")
            else:
                print(f"   🎯 Tendencia: ➡️ Estable")
    
    print("\n" + "=" * 80)
    conn.close()
    
except sqlite3.Error as e:
    print(f"❌ Error al conectar a la base de datos: {e}")
except Exception as e:
    print(f"❌ Error: {e}")
