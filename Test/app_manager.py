"""
🤖 RAG Ollama API - Manager Dashboard
Aplicación Streamlit para gestionar y probar todas las funcionalidades del sistema multi-agente.
"""

import streamlit as st
import requests
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

# Configuración de la API
API_BASE_URL = "http://localhost:8000"

# Ruta al archivo de configuración de categorías
CATEGORIES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "model_categories.json")

# ============================================================================
# Configuración de la página
# ============================================================================

st.set_page_config(
    page_title="RAG Ollama - API Manager",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# Funciones auxiliares
# ============================================================================

def check_api_health():
    """Verifica si la API está disponible."""
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=2)
        return response.status_code == 200
    except:
        return False

def api_request(method: str, endpoint: str, data: Optional[Dict] = None, files: Optional[Dict] = None, params: Optional[Dict] = None):
    """Realiza una petición a la API."""
    url = f"{API_BASE_URL}{endpoint}"
    try:
        if method == "GET":
            response = requests.get(url, params=params, timeout=30)
        elif method == "POST":
            if files:
                response = requests.post(url, files=files, params=params, timeout=60)
            else:
                response = requests.post(url, json=data, params=params, timeout=30)
        elif method == "PUT":
            response = requests.put(url, json=data, timeout=30)
        elif method == "DELETE":
            response = requests.delete(url, params=params, timeout=30)
        
        if response.status_code in [200, 201]:
            return True, response.json()
        else:
            # Intentar parsear JSON para obtener el detalle del error
            try:
                error_data = response.json()
                error_msg = error_data.get('detail') or error_data.get('error', response.text)
            except:
                error_msg = response.text
            return False, {"error": error_msg, "detail": error_msg, "status_code": response.status_code}
    except Exception as e:
        return False, {"error": str(e), "detail": str(e)}

def format_timestamp(ts_str: str) -> str:
    """Formatea un timestamp ISO para mejor legibilidad."""
    try:
        dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return ts_str

def load_model_categories() -> Dict:
    """Carga la configuración de categorías desde el archivo JSON."""
    try:
        if os.path.exists(CATEGORIES_FILE):
            with open(CATEGORIES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # Crear archivo con estructura por defecto
            default_config = {
                "_metadata": {
                    "description": "Configuración de categorías para modelos LLM",
                    "version": "1.0",
                    "last_updated": datetime.now().isoformat()
                },
                "categories": {}
            }
            save_model_categories(default_config)
            return default_config
    except Exception as e:
        st.error(f"Error al cargar categorías: {e}")
        return {"categories": {}}

def save_model_categories(config: Dict) -> bool:
    """Guarda la configuración de categorías en el archivo JSON."""
    try:
        # Actualizar metadata
        if "_metadata" in config:
            config["_metadata"]["last_updated"] = datetime.now().isoformat()
        
        # Asegurar que existe el directorio
        os.makedirs(os.path.dirname(CATEGORIES_FILE), exist_ok=True)
        
        with open(CATEGORIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        st.error(f"Error al guardar categorías: {e}")
        return False

def get_model_category(model_name: str, config: Dict) -> str:
    """Obtiene la categoría de un modelo específico.
    
    Primero busca en la lista exacta de modelos configurados,
    luego intenta con patrones si no encuentra coincidencia exacta.
    """
    categories = config.get("categories", {})
    
    # Búsqueda exacta primero
    for category, data in categories.items():
        if model_name in data.get("models", []):
            return category
    
    # Búsqueda por patrones
    model_lower = model_name.lower()
    for category, data in categories.items():
        patterns = data.get("patterns", [])
        if any(pattern.lower() in model_lower for pattern in patterns):
            return category
    
    # Si no encuentra ninguna categoría, devolver "Otros"
    return "🔧 Otros"

def assign_model_to_category(model_name: str, category: str) -> bool:
    """Asigna un modelo a una categoría específica."""
    config = load_model_categories()
    
    # Remover el modelo de cualquier otra categoría primero
    for cat, data in config.get("categories", {}).items():
        if model_name in data.get("models", []):
            data["models"].remove(model_name)
    
    # Agregar a la nueva categoría
    if category not in config.get("categories", {}):
        config["categories"][category] = {
            "description": "",
            "models": [],
            "patterns": []
        }
    
    if model_name not in config["categories"][category]["models"]:
        config["categories"][category]["models"].append(model_name)
    
    return save_model_categories(config)

def categorize_models(models: List[str]) -> Dict[str, List[str]]:
    """Categoriza modelos LLM por su propósito/uso usando la configuración persistente."""
    config = load_model_categories()
    categories_config = config.get("categories", {})
    
    # Inicializar categorías desde la configuración
    categorized = {cat: [] for cat in categories_config.keys()}
    
    # Si no hay categorías configuradas, usar las por defecto
    if not categorized:
        categorized = {
            "💬 Chatbot / Conversacional": [],
            "💻 Desarrollo / Código": [],
            "🧠 Razonamiento / Análisis": [],
            "🌍 Multilingüe": [],
            "📊 Embeddings": [],
            "⚡ Rápidos / Ligeros": [],
            "🎯 Especializados": [],
            "🔧 Otros": []
        }
    
    # Categorizar cada modelo
    for model in models:
        category = get_model_category(model, config)
        if category in categorized:
            categorized[category].append(model)
        else:
            # Si la categoría no existe, agregarlo a "Otros"
            if "🔧 Otros" in categorized:
                categorized["🔧 Otros"].append(model)
            else:
                categorized["🔧 Otros"] = [model]
    
    # Eliminar categorías vacías
    return {k: v for k, v in categorized.items() if v}

def create_categorized_options_list(models: List[str], include_global: bool = True) -> tuple[List[str], Dict[str, str]]:
    """Crea una lista de opciones con separadores categorizados y un mapeo para obtener el modelo real.
    
    Returns:
        tuple: (lista de opciones para mostrar, diccionario de mapeo display->model)
    """
    categorized = categorize_models(models)
    options = []
    mapping = {}
    
    if include_global:
        options.append("[Usar modelo global]")
        mapping["[Usar modelo global]"] = None
    
    for category, category_models in categorized.items():
        # Agregar separador de categoría (disabled visualmente)
        separator = f"─── {category} ───"
        options.append(separator)
        mapping[separator] = None  # No seleccionable
        
        # Agregar modelos de la categoría con indentación
        for model in category_models:
            display_name = f"  • {model}"
            options.append(display_name)
            mapping[display_name] = model
    
    return options, mapping

# ============================================================================
# Sidebar - Estado de la API
# ============================================================================

with st.sidebar:
    st.title("🤖 RAG Ollama API")
    st.markdown("---")
    
    # Estado de la API
    api_status = check_api_health()
    if api_status:
        st.success("✅ API Conectada")
    else:
        st.error("❌ API No Disponible")
        st.info("Asegúrate de que la API esté ejecutándose en http://localhost:8000")
        st.stop()
    
    st.markdown("---")
    st.markdown("### 📖 Guía Rápida")
    st.markdown("""
    **Pasos para comenzar:**
    1. 🤖 Crear un agente
    2. 📄 Cargar documentos (opcional)
    3. 💬 Iniciar conversación
    4. 📊 Monitorear sesiones
    """)
    
    st.markdown("---")
    if st.button("🔄 Refrescar Dashboard", use_container_width=True):
        st.rerun()

# ============================================================================
# Página Principal
# ============================================================================

st.title("🤖 RAG Ollama API - Dashboard de Gestión")
st.markdown("Interfaz completa para crear, gestionar y probar agentes conversacionales con RAG")

# Tabs principales
tabs = st.tabs([
    "🏠 Inicio",
    "🤖 Gestión de Agentes", 
    "💬 Chat & Conversación",
    "📄 Documentos",
    "�️ MCP SQLite",
    "📧 Email",
    "�📝 Sesiones",
    "🗄️ ChromaDB Admin",
    "🔧 Modelos Ollama",
    "🏷️ Categorías de Modelos"
])

# ============================================================================
# TAB 1: Inicio / Dashboard
# ============================================================================

with tabs[0]:
    st.header("📊 Estado del Sistema")
    
    col1, col2, col3 = st.columns(3)
    
    # Obtener estadísticas
    success, agents_data = api_request("GET", "/agents")
    
    if success:
        total_agents = agents_data.get("count", 0)
        col1.metric("🤖 Agentes Activos", total_agents)
    
    success, sessions_data = api_request("GET", "/sessions")
    if success:
        total_sessions = sessions_data.get("count", 0)
        col2.metric("📝 Sesiones Activas", total_sessions)
    
    success, collections_data = api_request("GET", "/chromadb/agents")
    if success:
        total_collections = collections_data.get("count", 0)
        total_docs = sum(c.get("count", 0) for c in collections_data.get("collections", []))
        col3.metric("📄 Documentos Totales", total_docs)
    
    st.markdown("---")
    
    # Información de agentes
    st.subheader("🤖 Agentes Disponibles")
    if success and agents_data.get("agents"):
        for agent in agents_data["agents"]:
            with st.expander(f"**{agent['name']}** (ID: `{agent['id']}`)", expanded=False):
                st.write(f"**Descripción:** {agent.get('description', 'Sin descripción')}")
                st.write(f"**Creado:** {format_timestamp(agent['created_at'])}")
                
                # Mostrar modelo LLM
                if agent.get('llm_model'):
                    st.write(f"**🤖 Modelo LLM:** `{agent['llm_model']}`")
                else:
                    st.write(f"**🤖 Modelo LLM:** *Usando modelo global*")
                
                # Obtener estadísticas del agente
                success_stats, stats = api_request("GET", f"/agents/{agent['id']}")
                if success_stats and "stats" in stats:
                    st_stats = stats["stats"]
                    
                    # Obtener conteo de documentos desde ChromaDB
                    doc_count = 0
                    success_docs, docs_info = api_request("GET", f"/chromadb/agents/{agent['id']}")
                    if success_docs:
                        doc_count = docs_info.get("count", 0)
                    
                    col_a, col_b, col_c = st.columns(3)
                    col_a.metric("💬 Sesiones", st_stats.get("active_sessions", 0))
                    col_b.metric("📨 Mensajes", st_stats.get("total_messages", 0))
                    col_c.metric("📄 Documentos", doc_count)
    else:
        st.info("No hay agentes creados. Ve a la pestaña **Gestión de Agentes** para crear uno.")

# ============================================================================
# TAB 2: Gestión de Agentes
# ============================================================================

with tabs[1]:
    st.header("🤖 Gestión de Agentes")
    
    col_left, col_right = st.columns([1, 1])
    
    # Columna izquierda: Crear/Editar
    with col_left:
        st.subheader("➕ Crear Nuevo Agente")
        
        # Obtener lista de modelos disponibles
        success_models, models_data = api_request("GET", "/ollama/models")
        available_models = []
        if success_models:
            models = models_data.get("models", [])
            # NO hacer split, usar nombre completo con tag
            available_models = [m.get("name", "") for m in models if m.get("name")]
            # Ordenar
            available_models = sorted(available_models)
        
        with st.form("create_agent_form"):
            agent_id = st.text_input(
                "ID del Agente*",
                placeholder="bot-asistente-legal",
                help="Identificador único (sin espacios, usar guiones)"
            )
            agent_name = st.text_input(
                "Nombre*",
                placeholder="Asistente Legal",
                help="Nombre descriptivo del agente"
            )
            agent_desc = st.text_area(
                "Descripción",
                placeholder="Especialista en consultas legales corporativas",
                help="Descripción breve de la función del agente"
            )
            agent_prompt = st.text_area(
                "Prompt del Sistema*",
                value="Eres un asistente útil y amigable.",
                height=150,
                help="Instrucciones que definen el comportamiento del agente"
            )
            
            # Campo para vincular BD SQLite personalizada
            st.markdown("---")
            st.markdown("#### 🗄️ Base de Datos SQLite (Opcional)")
            
            use_custom_db = st.checkbox(
                "🔗 Vincular Base de Datos SQLite personalizada",
                value=False,
                help="Permite al agente consultar una BD SQLite existente además del RAG vectorial"
            )
            
            sqlite_db_path = None
            if use_custom_db:
                sqlite_db_path = st.text_input(
                    "Ruta de la BD SQLite",
                    placeholder="Monitoring.db  o  ./data/custom.db  o  C:/databases/Sales.db",
                    help="Ruta al archivo .db (relativa o absoluta). Ejemplo: 'Monitoring.db'"
                )
                
                st.caption("""
                **💡 Vincula una BD existente para consultas estructuradas:**
                - `Monitoring.db` - Archivo en directorio actual
                - `./data/custom.db` - Ruta relativa
                - `C:/Proyectos/databases/Sales.db` - Ruta absoluta
                
                El agente podrá combinar RAG vectorial + consultas SQL automáticamente.
                """)
            
            st.markdown("---")
            st.markdown("#### 🔧 Configuración Avanzada")
            
            use_rag = st.checkbox(
                "📚 Habilitar RAG / ChromaDB",
                value=True,
                help="Si se deshabilita, el agente NO usará búsqueda vectorial de documentos (útil si ChromaDB no está disponible)"
            )
            
            if not use_rag:
                st.warning("⚠️ **RAG deshabilitado:** Este agente NO podrá consultar documentos de ChromaDB.")
            
            st.markdown("---")
            
            # Selector de modelo LLM
            use_custom_llm = st.checkbox(
                "🤖 Usar modelo LLM específico",
                value=False,
                help="Asignar un modelo LLM diferente para este agente. Si no se selecciona, usará el modelo global."
            )
            
            selected_llm = None
            if use_custom_llm:
                if available_models:
                    # Mostrar información de categorías
                    categorized = categorize_models(available_models)
                    st.caption(f"📋 {len(available_models)} modelos en {len(categorized)} categorías")
                    
                    with st.expander("ℹ️ Ver categorías disponibles", expanded=False):
                        for category, models in categorized.items():
                            st.markdown(f"**{category}** ({len(models)} modelos)")
                    
                    # Crear opciones organizadas con separadores
                    options, mapping = create_categorized_options_list(available_models, include_global=False)
                    
                    selected_display = st.selectbox(
                        "Modelo LLM",
                        options=options,
                        help="Selecciona el modelo específico (con tag incluido). Los modelos están organizados por categoría."
                    )
                    
                    # Obtener el modelo real desde el mapping
                    selected_llm = mapping.get(selected_display)
                    
                    # Si seleccionó un separador, mostrar advertencia
                    if selected_llm is None and selected_display != "[Usar modelo global]" and "───" in selected_display:
                        st.warning("⚠️ Los separadores no son seleccionables, elige un modelo de la lista")
                else:
                    st.warning("⚠️ No se pudieron cargar los modelos disponibles")
            
            submit = st.form_submit_button("🚀 Crear Agente", use_container_width=True, type="primary")
            
            if submit:
                if not agent_id or not agent_name or not agent_prompt:
                    st.error("⚠️ Completa todos los campos obligatorios (*)") 
                else:
                    data = {
                        "agent_id": agent_id,
                        "name": agent_name,
                        "prompt": agent_prompt,
                        "description": agent_desc if agent_desc else None
                    }
                    
                    # Agregar modelo LLM si se seleccionó
                    if use_custom_llm and selected_llm:
                        data["llm_model"] = selected_llm
                    
                    # Agregar ruta de BD SQLite si se seleccionó
                    if use_custom_db and sqlite_db_path:
                        data["sqlite_db_path"] = sqlite_db_path
                    
                    # Agregar configuración de RAG
                    data["use_rag"] = use_rag
                    
                    success, result = api_request("POST", "/agents", data=data)
                    
                    if success:
                        llm_info = f" con modelo {selected_llm}" if selected_llm else ""
                        db_info = f" y BD {sqlite_db_path}" if (use_custom_db and sqlite_db_path) else ""
                        st.success(f"✅ Agente '{agent_name}' creado exitosamente{llm_info}{db_info}!")
                        st.balloons()
                        st.rerun()
                    else:
                        error_msg = result.get('error') or result.get('detail', 'Error desconocido')
                        st.error(f"❌ Error: {error_msg}")
    
    # Columna derecha: Lista de agentes
    with col_right:
        st.subheader("📋 Agentes Existentes")
        
        success, agents_data = api_request("GET", "/agents")
        
        if success and agents_data.get("agents"):
            for agent in agents_data["agents"]:
                with st.container():
                    st.markdown(f"### {agent['name']}")
                    st.caption(f"ID: `{agent['id']}`")
                    
                    # Mostrar modelo LLM si está asignado
                    if agent.get('llm_model'):
                        st.caption(f"🤖 Modelo: `{agent['llm_model']}`")
                    else:
                        st.caption(f"🤖 Modelo: *global* (configurado en settings)")
                    
                    # Mostrar BD SQLite si está vinculada
                    if agent.get('sqlite_db_path'):
                        st.caption(f"🗄️ BD SQLite: `{agent['sqlite_db_path']}` ✅")
                    
                    # Mostrar estado de RAG
                    if not agent.get('use_rag', True):
                        st.caption(f"📚 RAG: ❌ Deshabilitado")
                    
                    st.write(agent.get("description", "Sin descripción"))
                    
                    col_a, col_b, col_c, col_d = st.columns(4)
                    
                    # Botón para ver detalles
                    with col_a:
                        if st.button(f"📊 Detalles", key=f"details_{agent['id']}"):
                            st.session_state[f"show_details_{agent['id']}"] = True
                    
                    # Botón para editar prompt
                    with col_b:
                        if st.button(f"✏️ Editar Prompt", key=f"edit_prompt_{agent['id']}"):
                            st.session_state[f"show_edit_prompt_{agent['id']}"] = True
                    
                    # Botón para editar modelo
                    with col_c:
                        if st.button(f"🤖 Modelo", key=f"edit_model_{agent['id']}"):
                            st.session_state[f"show_edit_model_{agent['id']}"] = True
                    
                    # Botón para eliminar
                    with col_d:
                        if agent["id"] != "default":
                            if st.button(f"🗑️ Eliminar", key=f"delete_{agent['id']}", type="secondary"):
                                st.session_state[f"confirm_delete_{agent['id']}"] = True
                    
                    # Mostrar detalles si se solicitó
                    if st.session_state.get(f"show_details_{agent['id']}", False):
                        with st.expander("📊 Detalles Completos", expanded=True):
                            st.json(agent)
                            if st.button("❌ Cerrar", key=f"close_{agent['id']}"):
                                st.session_state[f"show_details_{agent['id']}"] = False
                                st.rerun()
                    
                    # Mostrar formulario de edición de prompt
                    if st.session_state.get(f"show_edit_prompt_{agent['id']}", False):
                        with st.expander("✏️ Editar Prompt del Sistema", expanded=True):
                            st.info("📝 **Edita el prompt del sistema** que define el comportamiento del agente")
                            
                            current_prompt = agent.get('prompt', '')
                            
                            # Mostrar una vista previa del prompt actual (primeras líneas)
                            prompt_preview = current_prompt[:200] + "..." if len(current_prompt) > 200 else current_prompt
                            st.caption(f"**Prompt actual (preview):** {prompt_preview}")
                            
                            # Text area para editar el prompt
                            new_prompt = st.text_area(
                                "Nuevo Prompt del Sistema",
                                value=current_prompt,
                                height=400,
                                key=f"prompt_editor_{agent['id']}",
                                help="Define el comportamiento, personalidad y capacidades del agente"
                            )
                            
                            # Contador de caracteres
                            st.caption(f"📊 Longitud: {len(new_prompt)} caracteres ({len(new_prompt.split())} palabras)")
                            
                            col_save, col_cancel = st.columns(2)
                            with col_save:
                                if st.button("💾 Guardar Cambios", key=f"save_prompt_{agent['id']}", type="primary"):
                                    if not new_prompt.strip():
                                        st.error("⚠️ El prompt no puede estar vacío")
                                    else:
                                        update_data = {"prompt": new_prompt}
                                        
                                        with st.spinner("Actualizando prompt..."):
                                            success, result = api_request("PUT", f"/agents/{agent['id']}", data=update_data)
                                        
                                        if success:
                                            st.success(f"✅ Prompt actualizado exitosamente")
                                            st.balloons()
                                            st.session_state[f"show_edit_prompt_{agent['id']}"] = False
                                            st.rerun()
                                        else:
                                            error_detail = result.get('error', result.get('detail', 'Error desconocido'))
                                            st.error(f"❌ Error: {error_detail}")
                            
                            with col_cancel:
                                if st.button("❌ Cancelar", key=f"cancel_prompt_{agent['id']}"):
                                    st.session_state[f"show_edit_prompt_{agent['id']}"] = False
                                    st.rerun()
                    
                    # Mostrar formulario de edición de modelo
                    if st.session_state.get(f"show_edit_model_{agent['id']}", False):
                        with st.expander("🤖 Editar Modelo LLM", expanded=True):
                            # Obtener lista de modelos disponibles
                            success_models, models_data = api_request("GET", "/ollama/models")
                            
                            # Extraer modelos
                            raw_models = []
                            if success_models:
                                models = models_data.get("models", [])
                                # NO hacer split, usar nombre completo con tag
                                raw_models = [m.get("name", "") for m in models if m.get("name")]
                                raw_models = sorted(raw_models)
                            else:
                                st.warning("⚠️ No se pudieron cargar los modelos disponibles de Ollama")
                            
                            current_model = agent.get('llm_model')
                            
                            # Mostrar información
                            if raw_models:
                                categorized = categorize_models(raw_models)
                                st.info(f"📋 {len(raw_models)} modelos en {len(categorized)} categorías")
                            
                            # Mostrar el modelo actual del agente
                            if current_model:
                                st.success(f"**Modelo actual:** `{current_model}`")
                            else:
                                st.info("**Modelo actual:** *Usando modelo global*")
                            
                            # Mostrar categorías disponibles
                            if raw_models:
                                with st.expander("ℹ️ Ver categorías disponibles", expanded=False):
                                    for category, models in categorized.items():
                                        st.markdown(f"**{category}** ({len(models)} modelos)")
                                        for m in models:
                                            st.caption(f"  • {m}")
                            
                            # Crear opciones organizadas con separadores (incluir opción global)
                            options, mapping = create_categorized_options_list(raw_models, include_global=True)
                            
                            # Determinar índice por defecto
                            default_index = 0
                            # Buscar el modelo actual en las opciones display
                            if current_model:
                                display_current = f"  • {current_model}"
                                if display_current in options:
                                    default_index = options.index(display_current)
                            
                            selected_display = st.selectbox(
                                "Selecciona nuevo modelo",
                                options=options,
                                index=default_index,
                                key=f"model_select_{agent['id']}",
                                help="Selecciona un modelo de la lista. Los modelos están organizados por categoría."
                            )
                            
                            # Obtener el modelo real desde el mapping
                            new_model = mapping.get(selected_display)
                            
                            # Si seleccionó un separador, mostrar advertencia
                            if new_model is None and "───" in selected_display:
                                st.warning("⚠️ Los separadores no son seleccionables, elige un modelo de la lista")
                            
                            col_save, col_cancel = st.columns(2)
                            with col_save:
                                if st.button("💾 Guardar", key=f"save_model_{agent['id']}", type="primary"):
                                    # Validar que no sea un separador
                                    if "───" in selected_display:
                                        st.error("⚠️ No puedes seleccionar un separador. Elige un modelo de la lista.")
                                    else:
                                        # Preparar datos
                                        update_data = {}
                                        if new_model is None or selected_display == "[Usar modelo global]":
                                            update_data["llm_model"] = None  # Usar modelo global
                                        else:
                                            update_data["llm_model"] = new_model
                                        
                                        # Debug: mostrar qué se está enviando
                                        with st.spinner(f"Actualizando modelo..."):
                                            success, result = api_request("PUT", f"/agents/{agent['id']}", data=update_data)
                                        
                                        if success:
                                            model_msg = "modelo global" if new_model is None else new_model
                                            st.success(f"✅ Modelo actualizado a: {model_msg}")
                                            st.session_state[f"show_edit_model_{agent['id']}"] = False
                                            st.rerun()
                                        else:
                                            error_detail = result.get('error', result.get('detail', 'Error desconocido'))
                                            st.error(f"❌ Error: {error_detail}")
                                            # Mostrar debug info
                                            with st.expander("🔍 Debug Info"):
                                                st.write(f"**Modelo seleccionado:** `{new_model}`")
                                                st.write(f"**Display:** `{selected_display}`")
                                                st.write(f"**Datos enviados:** `{update_data}`")
                                                st.json(result)
                            
                            with col_cancel:
                                if st.button("❌ Cancelar", key=f"cancel_model_{agent['id']}"):
                                    st.session_state[f"show_edit_model_{agent['id']}"] = False
                                    st.rerun()
                    
                    # Confirmar eliminación
                    if st.session_state.get(f"confirm_delete_{agent['id']}", False):
                        st.warning(f"⚠️ ¿Eliminar agente '{agent['name']}'?")
                        col_yes, col_no = st.columns(2)
                        with col_yes:
                            if st.button("✅ Sí, eliminar", key=f"confirm_yes_{agent['id']}", type="primary"):
                                success, result = api_request("DELETE", f"/agents/{agent['id']}")
                                if success:
                                    st.success("✅ Agente eliminado")
                                    st.rerun()
                                else:
                                    st.error(f"❌ Error: {result.get('error')}")
                        with col_no:
                            if st.button("❌ Cancelar", key=f"confirm_no_{agent['id']}"):
                                st.session_state[f"confirm_delete_{agent['id']}"] = False
                                st.rerun()
                    
                    st.markdown("---")
        else:
            st.info("No hay agentes creados aún.")

# ============================================================================
# TAB 3: Chat & Conversación
# ============================================================================

with tabs[2]:
    st.header("💬 Chat & Conversación")
    
    # Seleccionar agente
    success, agents_data = api_request("GET", "/agents")
    
    if not success or not agents_data.get("agents"):
        st.warning("⚠️ Debes crear al menos un agente primero.")
    else:
        agents = agents_data["agents"]
        agent_options = {f"{a['name']} ({a['id']})": a['id'] for a in agents}
        
        col_config1, col_config2 = st.columns([2, 1])
        
        with col_config1:
            selected_agent_display = st.selectbox(
                "🤖 Selecciona un Agente",
                options=list(agent_options.keys())
            )
            agent_id = agent_options[selected_agent_display]
            
            # Obtener información del agente seleccionado
            success_agent, agent_info = api_request("GET", f"/agents/{agent_id}")
            if success_agent:
                llm_model = agent_info.get('llm_model')
                if llm_model:
                    st.info(f"🤖 Este agente usa el modelo: **{llm_model}**")
                else:
                    # Obtener el modelo global actual
                    success_current, current_data = api_request("GET", "/ollama/models/current")
                    if success_current:
                        global_model = current_data.get('chat_model', 'desconocido')
                        st.info(f"🤖 Este agente usa el modelo global: **{global_model}**")
        
        with col_config2:
            session_id = st.text_input(
                "🆔 Session ID",
                value="test-session-1",
                help="Puedes usar diferentes IDs para mantener conversaciones separadas"
            )
        
        st.markdown("---")
        
        # Configuración de RAG
        with st.expander("⚙️ Configuración Avanzada"):
            col_rag1, col_rag2, col_rag3, col_rag4 = st.columns(4)
            with col_rag1:
                use_rag = st.checkbox("Usar RAG", value=True, help="Recuperar contexto de documentos")
            with col_rag2:
                top_k = st.number_input("Top K", min_value=1, max_value=10, value=4, help="Número de chunks a recuperar")
            with col_rag3:
                temperature = st.slider("Temperature", min_value=0.0, max_value=1.0, value=0.7, step=0.1)
            with col_rag4:
                # Habilitar email solo si el agente tiene smtp_config
                agent_has_smtp = bool(agent_info.get("smtp_config")) if success_agent and agent_info else False
                use_email = st.checkbox(
                    "📧 Email",
                    value=agent_has_smtp,
                    disabled=not agent_has_smtp,
                    help="Permite al agente enviar emails (requiere SMTP configurado)" if agent_has_smtp else "Configura SMTP en el agente para habilitar emails"
                )
        
        # Historial de conversación
        st.subheader("💬 Conversación")
        
        # Obtener historial
        success, history_data = api_request("GET", f"/sessions/{agent_id}/{session_id}")
        
        if success and history_data.get("history"):
            for msg in history_data["history"]:
                if msg["role"] == "user":
                    st.chat_message("user").write(msg["content"])
                elif msg["role"] == "assistant":
                    st.chat_message("assistant").write(msg["content"])
        
        # Input para nuevo mensaje
        with st.form("chat_form", clear_on_submit=True):
            user_message = st.text_area(
                "Escribe tu mensaje:",
                placeholder="Hola, ¿cómo puedes ayudarme?",
                height=100
            )
            send_button = st.form_submit_button("📤 Enviar", use_container_width=True, type="primary")
            
            if send_button and user_message:
                with st.spinner("🤔 Pensando..."):
                    data = {
                        "message": user_message,
                        "agent_id": agent_id,
                        "session_id": session_id,
                        "use_rag": use_rag,
                        "use_email": use_email,
                        "top_k": top_k,
                        "temperature": temperature
                    }
                    success, result = api_request("POST", "/chat", data=data)
                    
                    if success:
                        st.rerun()
                    else:
                        st.error(f"❌ Error: {result.get('error')}")
        
        # Botón para limpiar conversación
        if st.button("🗑️ Limpiar Historial de esta Sesión"):
            success, result = api_request("DELETE", f"/sessions/{agent_id}/{session_id}")
            if success:
                st.success("✅ Historial limpiado")
                st.rerun()

# ============================================================================
# TAB 4: Documentos
# ============================================================================

with tabs[3]:
    st.header("📄 Gestión de Documentos")
    
    # Seleccionar agente
    success, agents_data = api_request("GET", "/agents")
    
    if not success or not agents_data.get("agents"):
        st.warning("⚠️ Debes crear al menos un agente primero.")
    else:
        agents = agents_data["agents"]
        agent_options = {f"{a['name']} ({a['id']})": a['id'] for a in agents}
        
        col_doc1, col_doc2 = st.columns([1, 1])
        
        # Columna izquierda: Cargar documento
        with col_doc1:
            st.subheader("📤 Cargar Documento")
            
            selected_agent_display = st.selectbox(
                "🤖 Asignar a Agente",
                options=list(agent_options.keys()),
                key="doc_agent_select"
            )
            agent_id = agent_options[selected_agent_display]
            
            uploaded_file = st.file_uploader(
                "Selecciona un archivo",
                type=["pdf", "txt", "json", "xml", "csv"],
                help="Soporta: PDF, TXT, JSON, XML, CSV. El documento será procesado y embebido en la base de conocimientos del agente"
            )
            
            if uploaded_file:
                # Detectar tipo MIME según extensión
                file_extension = uploaded_file.name.split('.')[-1].lower()
                mime_types = {
                    "pdf": "application/pdf",
                    "txt": "text/plain",
                    "json": "application/json",
                    "xml": "application/xml",
                    "csv": "text/csv"
                }
                mime_type = mime_types.get(file_extension, "application/octet-stream")
                
                st.info(f"📄 Archivo: {uploaded_file.name} ({uploaded_file.size / 1024:.2f} KB) - Tipo: {file_extension.upper()}")
                
                # Campos de metadata del documento
                st.markdown("**📋 Información del Documento**")
                doc_title = st.text_input(
                    "Título del Documento",
                    value=uploaded_file.name.rsplit('.', 1)[0],
                    help="Título descriptivo que identifica el contenido del documento",
                    key="doc_title_input"
                )
                doc_version = st.text_input(
                    "Versión",
                    value="1.0",
                    help="Versión del documento (ej: 1.0, v2.3, 2024-Q1)",
                    key="doc_version_input"
                )
                doc_country = st.text_input(
                    "País",
                    value="",
                    placeholder="Panamá, México, Colombia, etc.",
                    help="País al que pertenece este documento",
                    key="doc_country_input"
                )
                
                if st.button("🚀 Procesar y Cargar", type="primary", use_container_width=True):
                    with st.spinner("📊 Procesando documento..."):
                        files = {"upload": (uploaded_file.name, uploaded_file, mime_type)}
                        params = {
                            "agent_id": agent_id,
                            "document_title": doc_title,
                            "document_version": doc_version,
                            "country": doc_country if doc_country else None
                        }
                        success, result = api_request("POST", "/ingest", files=files, params=params)
                        
                        if success:
                            st.success(f"✅ Documento procesado: {result.get('chunks', 0)} chunks creados")
                            country_info = f" | 🌎 País: {result.get('country')}" if result.get('country') and result.get('country') != 'N/A' else ""
                            st.info(f"📝 Título: {result.get('title')} | Versión: {result.get('version')}{country_info}")
                            st.balloons()
                        else:
                            st.error(f"❌ Error: {result.get('error')}")
        
        # Columna derecha: Ver documentos cargados
        with col_doc2:
            st.subheader("📚 Documentos por Agente")
            
            # Mostrar documentos de cada agente
            success, collections_data = api_request("GET", "/chromadb/agents")
            
            if success and collections_data.get("collections"):
                for collection in collections_data["collections"]:
                    agent_id_col = collection["agent_id"]
                    doc_count = collection.get("count", 0)
                    
                    # Buscar nombre del agente
                    agent_name = next((a["name"] for a in agents if a["id"] == agent_id_col), agent_id_col)
                    
                    with st.expander(f"**{agent_name}** - {doc_count} documentos"):
                        st.write(f"**Colección:** `{collection['collection_name']}`")
                        
                        if doc_count > 0:
                            # Botón para ver preview
                            if st.button(f"👁️ Ver Preview", key=f"preview_{agent_id_col}"):
                                success_docs, docs_data = api_request("GET", f"/chromadb/agents/{agent_id_col}/documents")
                                if success_docs:
                                    # Mostrar metadata de forma estructurada
                                    st.write(f"**Total de chunks:** {docs_data.get('count', 0)}")
                                    
                                    # Agrupar por documento (usando metadata)
                                    metadatas = docs_data.get('metadatas', [])
                                    if metadatas and len(metadatas) > 0:
                                        # Obtener documentos únicos
                                        unique_docs = {}
                                        for meta in metadatas:
                                            if meta:
                                                title = meta.get('title', meta.get('filename', 'Sin título'))
                                                if title not in unique_docs:
                                                    unique_docs[title] = {
                                                        'title': title,
                                                        'version': meta.get('version', 'N/A'),
                                                        'country': meta.get('country', 'N/A'),
                                                        'filename': meta.get('filename', 'N/A'),
                                                        'file_type': meta.get('file_type', 'N/A'),
                                                        'total_chunks': meta.get('total_chunks', 0),
                                                        'ingested_at': meta.get('ingested_at', 'N/A')
                                                    }
                                        
                                        st.write("**📄 Documentos únicos:**")
                                        for doc_info in unique_docs.values():
                                            with st.container():
                                                country_display = f" 🌎 {doc_info['country']}" if doc_info['country'] != 'N/A' else ""
                                                st.markdown(f"- **{doc_info['title']}** (v{doc_info['version']}){country_display}")
                                                st.caption(f"   Archivo: {doc_info['filename']} | Tipo: {doc_info['file_type']} | Chunks: {doc_info['total_chunks']} | Fecha: {doc_info['ingested_at'][:10]}")
                                    
                                    # Opción para ver JSON completo
                                    if st.checkbox("Ver JSON completo", key=f"json_{agent_id_col}"):
                                        st.json(docs_data)
                            
                            # Botón para eliminar documentos
                            if st.button(f"🗑️ Eliminar Documentos", key=f"delete_docs_{agent_id_col}", type="secondary"):
                                success_del, result = api_request("DELETE", f"/chromadb/agents/{agent_id_col}")
                                if success_del:
                                    st.success("✅ Documentos eliminados")
                                    st.rerun()
                        else:
                            st.info("Sin documentos cargados")
            else:
                st.info("No hay documentos cargados en ningún agente.")

# ============================================================================
# TAB 5: MCP SQLite
# ============================================================================

with tabs[4]:
    st.header("🗄️ MCP SQLite - Datos Estructurados")
    
    st.markdown("""
    **Model Context Protocol (MCP)** permite a los agentes consultar bases de datos SQLite además del RAG vectorial.
    Cada agente puede tener su propia BD automática o vincular una BD personalizada.
    """)
    
    tab_mcp = st.tabs([
        "📊 Dashboard",
        "🔗 Vincular BD a Agente",
        "💾 Consultar Bases de Datos",
        "📈 Estadísticas SQL",
        "🔧 Administración"
    ])
    
    # ==================== SUB-TAB 1: Dashboard ====================
    with tab_mcp[0]:
        st.subheader("📊 Estado de MCP SQLite")
        
        col1, col2, col3 = st.columns(3)
        
        # Obtener bases de datos disponibles
        success_dbs, dbs_data = api_request("GET", "/mcp/databases")
        
        if success_dbs:
            agent_dbs = dbs_data.get("databases", {}).get("agents", [])
            system_dbs = dbs_data.get("databases", {}).get("system", [])
            
            col1.metric("🤖 BDs de Agentes", len(agent_dbs))
            col2.metric("⚙️ BDs del Sistema", len(system_dbs))
            col3.metric("📊 Total BDs", len(agent_dbs) + len(system_dbs))
            
            st.markdown("---")
            
            # Mostrar agentes con BD vinculada
            st.subheader("🤖 Agentes con SQLite")
            
            success_agents, agents_data = api_request("GET", "/agents")
            
            if success_agents and agents_data.get("agents"):
                for agent in agents_data["agents"]:
                    with st.expander(f"**{agent['name']}** (`{agent['id']}`)", expanded=False):
                        cols = st.columns([3, 1])
                        
                        with cols[0]:
                            # Verificar si tiene BD personalizada
                            custom_db = agent.get("sqlite_db_path")
                            if custom_db:
                                st.success(f"✅ **BD Personalizada:** `{custom_db}`")
                                st.caption("Este agente consulta una base de datos específica")
                            else:
                                if f"agent_{agent['id']}" in agent_dbs:
                                    st.info(f"📦 **BD Automática:** `agent_{agent['id']}.db`")
                                    st.caption("Base de datos generada automáticamente para logs y métricas")
                                else:
                                    st.warning("⚠️ **Sin BD:** No inicializada")
                        
                        with cols[1]:
                            # Botón para inicializar
                            if f"agent_{agent['id']}" not in agent_dbs and not custom_db:
                                if st.button("🔧 Inicializar", key=f"init_{agent['id']}"):
                                    success_init, result = api_request("POST", f"/mcp/agents/{agent['id']}/init")
                                    if success_init:
                                        st.success("✅ BD inicializada")
                                        st.rerun()
                            
                            # Botón para ver estadísticas
                            if st.button("📊 Stats", key=f"stats_{agent['id']}"):
                                success_stats, stats = api_request("GET", f"/mcp/agents/{agent['id']}/stats")
                                if success_stats:
                                    st.json(stats)
        else:
            st.error("❌ Error al cargar bases de datos")
    
    # ==================== SUB-TAB 2: Vincular BD ====================
    with tab_mcp[1]:
        st.subheader("🔗 Vincular Base de Datos Personalizada")
        
        st.info("""
        **💡 Vincula una BD SQLite existente a un agente**
        
        El agente podrá consultar tu BD + RAG simultáneamente. Ideal para:
        - Bases de datos de monitoreo (Monitoring.db)
        - Datos de ventas o clientes
        - Logs de sistemas
        - Cualquier BD SQLite personalizada
        """)
        
        # Seleccionar agente
        success_agents, agents_data = api_request("GET", "/agents")
        
        if not success_agents or not agents_data.get("agents"):
            st.warning("⚠️ Debes crear al menos un agente primero.")
        else:
            agents = agents_data["agents"]
            agent_options = {f"{a['name']} ({a['id']})": a['id'] for a in agents}
            
            col_link1, col_link2 = st.columns([2, 1])
            
            with col_link1:
                selected_agent_display = st.selectbox(
                    "Selecciona un agente",
                    options=list(agent_options.keys()),
                    key="link_agent_select"
                )
                agent_id = agent_options[selected_agent_display]
                
                # Mostrar BD actual si existe
                selected_agent_data = next(a for a in agents if a["id"] == agent_id)
                current_db = selected_agent_data.get("sqlite_db_path")
                
                if current_db:
                    st.warning(f"⚠️ **BD actual:** `{current_db}`")
                    st.caption("Puedes cambiarla usando el formulario de actualización")
                else:
                    st.info("✨ Este agente no tiene BD personalizada vinculada")
            
            st.markdown("---")
            
            # Formulario para vincular/actualizar BD
            with st.form("link_db_form"):
                st.markdown("#### 📁 Ruta de la Base de Datos")
                
                db_path = st.text_input(
                    "Ruta de la BD (relativa o absoluta)",
                    placeholder="Monitoring.db  o  ./data/custom.db  o  C:/databases/Sales.db",
                    help="Ruta al archivo .db. Ejemplos: 'Monitoring.db', './data/custom.db', ruta absoluta"
                )
                
                st.caption("""
                **Rutas soportadas:**
                - `Monitoring.db` - Archivo en directorio actual
                - `./data/Monitoring.db` - Ruta relativa
                - `C:/Proyectos/databases/Monitoring.db` - Ruta absoluta (Windows)
                - `/home/user/databases/Monitoring.db` - Ruta absoluta (Linux)
                """)
                
                col_submit, col_remove = st.columns(2)
                
                with col_submit:
                    submit_link = st.form_submit_button("🔗 Vincular / Actualizar BD", type="primary", use_container_width=True)
                
                with col_remove:
                    remove_link = st.form_submit_button("🗑️ Desvincular BD", type="secondary", use_container_width=True)
                
                if submit_link:
                    if not db_path:
                        st.error("⚠️ Debes especificar una ruta")
                    else:
                        # Actualizar agente con la nueva BD
                        update_data = {"sqlite_db_path": db_path}
                        success, result = api_request("PUT", f"/agents/{agent_id}", data=update_data)
                        
                        if success:
                            st.success(f"✅ BD vinculada: {db_path}")
                            st.info("💡 La BD se copiará automáticamente a `mcp_sqlite/databases/custom/` al usarla")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error(f"❌ Error: {result.get('error')}")
                
                if remove_link:
                    if not current_db:
                        st.warning("⚠️ Este agente no tiene BD vinculada")
                    else:
                        # Desvincular (establecer a None)
                        update_data = {"sqlite_db_path": None}
                        success, result = api_request("PUT", f"/agents/{agent_id}", data=update_data)
                        
                        if success:
                            st.success("✅ BD desvinculada")
                            st.info("El agente usará su BD automática (si está inicializada)")
                            st.rerun()
                        else:
                            st.error(f"❌ Error: {result.get('error')}")
            
            st.markdown("---")
            
            # Ejemplo práctico
            with st.expander("📖 Ejemplo: Vincular Monitoring.db", expanded=False):
                st.code("""
# 1. Coloca tu archivo Monitoring.db en el directorio del proyecto
# 2. En el formulario arriba, ingresa: Monitoring.db
# 3. Click en "Vincular / Actualizar BD"
# 4. Ahora el agente puede consultar Monitoring.db en el chat
                
# Ejemplo de pregunta:
"¿Cuáles son los últimos errores registrados en el sistema?"

# El agente consultará automáticamente Monitoring.db + RAG
                """, language="python")
    
    # ==================== SUB-TAB 3: Consultar BDs ====================
    with tab_mcp[2]:
        st.subheader("💾 Ejecutar Consultas SQL")
        
        # Seleccionar agente
        success_agents, agents_data = api_request("GET", "/agents")
        
        if not success_agents or not agents_data.get("agents"):
            st.warning("⚠️ Debes crear al menos un agente primero.")
        else:
            agents = agents_data["agents"]
            agent_options = {f"{a['name']} ({a['id']})": a['id'] for a in agents}
            
            selected_agent_display = st.selectbox(
                "Selecciona un agente",
                options=list(agent_options.keys()),
                key="query_agent_select"
            )
            agent_id = agent_options[selected_agent_display]
            
            # Obtener esquema de la BD
            col_schema1, col_schema2 = st.columns([2, 1])
            
            with col_schema1:
                st.markdown("#### 📋 Esquema de la Base de Datos")
            
            with col_schema2:
                if st.button("🔄 Obtener Esquema", use_container_width=True):
                    with st.spinner("Cargando esquema..."):
                        success_schema, schema = api_request("GET", f"/mcp/databases/agent_{agent_id}/schema")
                        
                        if success_schema and schema.get("success"):
                            st.session_state[f"schema_{agent_id}"] = schema
                        else:
                            st.error("❌ Error al obtener esquema. ¿La BD está inicializada?")
            
            # Mostrar esquema si existe
            if f"schema_{agent_id}" in st.session_state:
                schema = st.session_state[f"schema_{agent_id}"]
                tables = schema.get("tables", {})
                
                with st.expander(f"📊 Tablas disponibles ({len(tables)})", expanded=True):
                    for table_name, columns in tables.items():
                        st.markdown(f"**{table_name}** ({len(columns)} columnas)")
                        
                        # Mostrar columnas en formato tabla
                        cols_data = []
                        for col in columns:
                            cols_data.append({
                                "Columna": col["name"],
                                "Tipo": col["type"],
                                "NOT NULL": "✓" if col.get("notnull") else "",
                                "PK": "✓" if col.get("primary_key") else ""
                            })
                        
                        if cols_data:
                            import pandas as pd
                            df = pd.DataFrame(cols_data)
                            st.dataframe(df, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            
            # Formulario de consulta
            st.markdown("#### 🔍 Ejecutar Consulta SQL")
            
            tab_query_type = st.tabs(["📖 SELECT (Lectura)", "✏️ INSERT/UPDATE/DELETE (Escritura)"])
            
            # Tab de SELECT
            with tab_query_type[0]:
                with st.form("select_query_form"):
                    query_select = st.text_area(
                        "Consulta SQL (SELECT)",
                        value="SELECT * FROM agent_logs ORDER BY timestamp DESC LIMIT 10",
                        height=120,
                        help="Solo consultas SELECT"
                    )
                    
                    # Plantillas comunes
                    col_t1, col_t2, col_t3 = st.columns(3)
                    
                    with col_t1:
                        if st.form_submit_button("📝 Logs Recientes"):
                            st.session_state["query_template"] = "SELECT * FROM agent_logs ORDER BY timestamp DESC LIMIT 10"
                            st.rerun()
                    
                    with col_t2:
                        if st.form_submit_button("📊 Métricas"):
                            st.session_state["query_template"] = "SELECT metric_name, AVG(metric_value) as avg_value FROM agent_metrics GROUP BY metric_name"
                            st.rerun()
                    
                    with col_t3:
                        if st.form_submit_button("📄 Documentos"):
                            st.session_state["query_template"] = "SELECT filename, chunks_count, processed_at FROM processed_documents ORDER BY processed_at DESC"
                            st.rerun()
                    
                    submit_select = st.form_submit_button("▶️ Ejecutar SELECT", type="primary", use_container_width=True)
                    
                    if submit_select:
                        if not query_select.strip():
                            st.error("⚠️ Ingresa una consulta SQL")
                        else:
                            with st.spinner("Ejecutando consulta..."):
                                data = {"query": query_select}
                                success, result = api_request("POST", f"/mcp/agents/{agent_id}/query", data=data)
                                
                                if success and result.get("success"):
                                    rows = result.get("rows", [])
                                    st.success(f"✅ Consulta exitosa: {len(rows)} filas")
                                    
                                    if rows:
                                        import pandas as pd
                                        df = pd.DataFrame(rows)
                                        st.dataframe(df, use_container_width=True)
                                        
                                        # Opción para ver JSON
                                        with st.expander("🔍 Ver JSON"):
                                            st.json(result)
                                    else:
                                        st.info("Sin resultados")
                                else:
                                    error_msg = result.get("error", "Error desconocido")
                                    st.error(f"❌ Error: {error_msg}")
            
            # Tab de escritura
            with tab_query_type[1]:
                st.warning("⚠️ **Precaución:** Las operaciones de escritura modifican la base de datos permanentemente.")
                
                with st.form("write_query_form"):
                    query_write = st.text_area(
                        "Consulta SQL (INSERT/UPDATE/DELETE)",
                        placeholder="INSERT INTO custom_data (data_key, data_value) VALUES ('key1', 'value1')",
                        height=120,
                        help="Operaciones de escritura"
                    )
                    
                    submit_write = st.form_submit_button("▶️ Ejecutar Escritura", type="primary", use_container_width=True)
                    
                    if submit_write:
                        if not query_write.strip():
                            st.error("⚠️ Ingresa una consulta SQL")
                        else:
                            # Pedir confirmación
                            st.warning("⚠️ ¿Confirmas que deseas ejecutar esta operación de escritura?")
                            if st.checkbox("Sí, estoy seguro", key="confirm_write"):
                                with st.spinner("Ejecutando..."):
                                    data = {"query": query_write}
                                    success, result = api_request("POST", f"/mcp/agents/{agent_id}/write", data=data)
                                    
                                    if success and result.get("success"):
                                        rows_affected = result.get("rows_affected", 0)
                                        st.success(f"✅ Operación exitosa: {rows_affected} filas afectadas")
                                        st.json(result)
                                    else:
                                        error_msg = result.get("error", "Error desconocido")
                                        st.error(f"❌ Error: {error_msg}")
    
    # ==================== SUB-TAB 4: Estadísticas ====================
    with tab_mcp[3]:
        st.subheader("📈 Estadísticas SQL de Agentes")
        
        # Seleccionar agente
        success_agents, agents_data = api_request("GET", "/agents")
        
        if not success_agents or not agents_data.get("agents"):
            st.warning("⚠️ Debes crear al menos un agente primero.")
        else:
            agents = agents_data["agents"]
            agent_options = {f"{a['name']} ({a['id']})": a['id'] for a in agents}
            
            selected_agent_display = st.selectbox(
                "Selecciona un agente",
                options=list(agent_options.keys()),
                key="stats_agent_select"
            )
            agent_id = agent_options[selected_agent_display]
            
            if st.button("📊 Cargar Estadísticas", type="primary", use_container_width=True):
                with st.spinner("Cargando estadísticas..."):
                    success_stats, stats = api_request("GET", f"/mcp/agents/{agent_id}/stats")
                    
                    if success_stats:
                        st.session_state[f"stats_data_{agent_id}"] = stats
                    else:
                        st.error("❌ Error al cargar estadísticas")
            
            # Mostrar estadísticas si existen
            if f"stats_data_{agent_id}" in st.session_state:
                stats_data = st.session_state[f"stats_data_{agent_id}"]
                statistics = stats_data.get("statistics", {})
                
                st.markdown("---")
                
                # Métricas principales
                col1, col2, col3, col4 = st.columns(4)
                
                col1.metric("📝 Total Logs", statistics.get("total_logs", 0))
                col2.metric("📊 Total Métricas", statistics.get("total_metrics", 0))
                col3.metric("📄 Documentos", statistics.get("total_documents", 0))
                
                st.markdown("---")
                
                # Logs por acción
                st.subheader("📝 Logs por Tipo de Acción")
                logs_by_action = statistics.get("logs_by_action", [])
                
                if logs_by_action:
                    import pandas as pd
                    df_logs = pd.DataFrame(logs_by_action)
                    
                    col_chart, col_table = st.columns([2, 1])
                    
                    with col_chart:
                        st.bar_chart(df_logs.set_index("action")["count"])
                    
                    with col_table:
                        st.dataframe(df_logs, use_container_width=True, hide_index=True)
                else:
                    st.info("Sin datos de logs")
                
                st.markdown("---")
                
                # Métricas recientes
                st.subheader("📊 Métricas Recientes")
                recent_metrics = statistics.get("recent_metrics", [])
                
                if recent_metrics:
                    import pandas as pd
                    df_metrics = pd.DataFrame(recent_metrics)
                    st.dataframe(df_metrics, use_container_width=True, hide_index=True)
                else:
                    st.info("Sin métricas registradas")
    
    # ==================== SUB-TAB 5: Administración ====================
    with tab_mcp[4]:
        st.subheader("🔧 Administración de MCP SQLite")
        
        st.markdown("#### 📁 Ubicación de Bases de Datos")
        st.code("""
mcp_sqlite/databases/
├── agents/              # BDs automáticas por agente
│   └── agent_{id}.db
├── system/              # BDs del sistema
│   └── system_metrics.db
└── custom/              # BDs personalizadas vinculadas
    ├── Monitoring.db
    └── ...
        """)
        
        st.markdown("---")
        
        # Listar todas las BDs
        st.markdown("#### 📊 Bases de Datos Disponibles")
        
        if st.button("🔄 Refrescar Lista", key="refresh_mcp_databases", use_container_width=True):
            st.rerun()
        
        success_dbs, dbs_data = api_request("GET", "/mcp/databases")
        
        if success_dbs and dbs_data.get("success"):
            databases = dbs_data.get("databases", {})
            
            col_db1, col_db2 = st.columns(2)
            
            with col_db1:
                st.markdown("##### 🤖 Bases de Datos de Agentes")
                agent_dbs = databases.get("agents", [])
                if agent_dbs:
                    for db in agent_dbs:
                        st.text(f"• {db}.db")
                else:
                    st.info("Sin BDs de agentes")
            
            with col_db2:
                st.markdown("##### ⚙️ Bases de Datos del Sistema")
                system_dbs = databases.get("system", [])
                if system_dbs:
                    for db in system_dbs:
                        st.text(f"• {db}.db")
                else:
                    st.info("Sin BDs del sistema")
        
        st.markdown("---")
        
        # Documentación rápida
        with st.expander("📖 Documentación MCP SQLite", expanded=False):
            st.markdown("""
            ### ¿Cómo funciona MCP SQLite?
            
            **Model Context Protocol (MCP)** permite consultar datos estructurados junto con RAG:
            
            1. **BD Automática por Agente**
               - Se crea automáticamente: `agent_{id}.db`
               - Tablas: logs, métricas, documentos, config, conversaciones
               - Ideal para tracking interno
            
            2. **BD Personalizada Vinculada**
               - Vincula cualquier .db existente (ej: Monitoring.db)
               - El agente consulta TU base de datos
               - Se copia a `mcp_sqlite/databases/custom/`
            
            3. **Uso Híbrido (RAG + SQL)**
               - En el chat, activa `use_sql=true`
               - El agente combina documentos vectoriales + datos SQLite
               - Respuestas enriquecidas con contexto estructurado
            
            ### Tablas Automáticas
            
            Cada BD de agente incluye:
            - `agent_logs` - Registro de acciones
            - `agent_metrics` - Métricas numéricas
            - `processed_documents` - Documentos ingresados
            - `agent_config` - Configuración key-value
            - `conversations` - Historial de chat
            - `rag_statistics` - Stats de búsquedas
            - `custom_data` - Datos personalizados
            
            ### Ejemplo Práctico
            
            ```python
            # 1. Crear agente con BD personalizada
            POST /agents
            {
              "sqlite_db_path": "Monitoring.db"
            }
            
            # 2. Chatear con SQL habilitado
            POST /chat
            {
              "use_sql": true,
              "message": "¿Cuáles son los últimos errores?"
            }
            
            # El agente consulta:
            # - Monitoring.db (datos estructurados)
            # - ChromaDB (documentos vectoriales)
            # = Respuesta híbrida
            ```
            
            ### Documentación Completa
            
            - [MCP_INTEGRATION.md](http://localhost:8000/docs)
            - [VINCULAR_BD_PERSONALIZADA.md](http://localhost:8000/docs)
            """)

# ============================================================================
# TAB 6: Email (SMTP)
# ============================================================================

with tabs[5]:
    st.header("📧 Gestión de Emails (SMTP)")
    st.markdown("Envía emails desde tus agentes usando SMTP. Soporta Gmail, Outlook, Yahoo y servidores personalizados.")
    
    # Advertencia de troubleshooting si hay problemas
    with st.expander("🆘 Ayuda y Troubleshooting", expanded=False):
        st.markdown("""
        ### 🔧 Problemas Comunes
        
        #### 1. Error de Timeout / No se puede conectar
        **Causas:**
        - Firewall o antivirus bloqueando la conexión
        - Servidor o puerto incorrectos
        - Problemas de red/internet
        
        **Soluciones:**
        - Usa el botón "🔍 Probar Conexión" antes de guardar
        - Desactiva temporalmente firewall/antivirus
        - Verifica que uses el puerto correcto (587 para TLS, 465 para SSL)
        - Prueba tu conexión con otro cliente de email primero
        
        #### 2. Error de Autenticación
        **Para Gmail/Yahoo:**
        - NO uses tu contraseña normal
        - Debes generar un App Password:
          - Gmail: https://myaccount.google.com/apppasswords (requiere 2FA activado)
          - Yahoo: https://login.yahoo.com/account/security
        
        **Para Outlook/Office365:**
        - Puedes usar tu contraseña normal
        - Si falla, verifica que tu cuenta no tenga 2FA sin configurar
        
        #### 3. Rate Limits (demasiados emails)
        - Gmail gratis: 500/día, 2000/día (Workspace)
        - Outlook: 300/día
        - Yahoo: 500/día
        
        ### ✅ Mejores Prácticas
        - Siempre prueba con un email de prueba primero
        - Usa App Passwords cuando sea requerido
        - Verifica la configuración con "🔍 Probar Conexión"
        - Para producción, considera servicios especializados (SendGrid, Mailgun)
        """)
    
    # Sub-tabs para Email
    tab_email = st.tabs([
        "📤 Enviar Email",
        "⚙️ Proveedores SMTP",
        "🤖 Configurar Agente",
        "📊 Historial"
    ])
    
    # ==================== SUB-TAB 1: Enviar Email ====================
    with tab_email[0]:
        st.subheader("📤 Enviar Email desde un Agente")
        
        # Listar agentes con SMTP configurado
        success_agents, agents_data = api_request("GET", "/agents")
        
        if success_agents:
            agents = agents_data.get("agents", [])
            agents_with_smtp = [a for a in agents if a.get("smtp_config")]
            agents_without_smtp = [a for a in agents if not a.get("smtp_config")]
            
            if not agents_with_smtp:
                st.warning("⚠️ No hay agentes con configuración SMTP. Configura un agente en la pestaña '🤖 Configurar Agente'")
            else:
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    selected_agent_id = st.selectbox(
                        "Agente remitente:",
                        options=[a["id"] for a in agents_with_smtp],
                        format_func=lambda x: next((a["name"] for a in agents_with_smtp if a["id"] == x), x)
                    )
                    
                    selected_agent = next((a for a in agents_with_smtp if a["id"] == selected_agent_id), None)
                    
                    if selected_agent:
                        smtp = selected_agent.get("smtp_config", {})
                        st.info(f"📧 Remitente: **{smtp.get('email', 'N/A')}** | Servidor: {smtp.get('server', 'N/A')}")
                
                with col2:
                    st.metric("Agentes con SMTP", len(agents_with_smtp))
                    st.metric("Sin SMTP", len(agents_without_smtp))
                
                st.markdown("---")
                
                # Formulario de envío
                col_form1, col_form2 = st.columns([2, 1])
                
                with col_form1:
                    to_email = st.text_input(
                        "Destinatario (To):",
                        placeholder="usuario@example.com",
                        help="Email del destinatario principal"
                    )
                    
                    subject = st.text_input(
                        "Asunto:",
                        placeholder="Asunto del mensaje",
                        help="Título del email"
                    )
                    
                    body = st.text_area(
                        "Cuerpo del mensaje:",
                        placeholder="Escribe aquí el contenido del email...",
                        height=200,
                        help="Contenido del mensaje"
                    )
                
                with col_form2:
                    cc_emails = st.text_area(
                        "CC (opcional):",
                        placeholder="email1@example.com\nemail2@example.com",
                        height=80,
                        help="Un email por línea"
                    )
                    
                    bcc_emails = st.text_area(
                        "BCC (opcional):",
                        placeholder="email1@example.com\nemail2@example.com",
                        height=80,
                        help="Un email por línea"
                    )
                    
                    html_mode = st.checkbox("Formato HTML", value=False, help="Interpretar el cuerpo como HTML")
                
                if st.button("📤 Enviar Email", type="primary", use_container_width=True):
                    if not to_email or not subject or not body:
                        st.error("⚠️ Completa al menos: Destinatario, Asunto y Cuerpo")
                    else:
                        # Preparar datos
                        cc_list = [email.strip() for email in cc_emails.split("\n") if email.strip()]
                        bcc_list = [email.strip() for email in bcc_emails.split("\n") if email.strip()]
                        
                        email_data = {
                            "agent_id": selected_agent_id,
                            "to": to_email,
                            "subject": subject,
                            "body": body,
                            "cc": cc_list,
                            "bcc": bcc_list,
                            "html": html_mode
                        }
                        
                        with st.spinner("Enviando email..."):
                            success, result = api_request("POST", "/email/send", data=email_data)
                        
                        if success:
                            st.success(f"✅ {result.get('message', 'Email enviado exitosamente')}")
                            st.balloons()
                            
                            # Mostrar detalles
                            with st.expander("📋 Detalles del envío"):
                                st.json(result)
                        else:
                            error_detail = result.get('detail', 'Error desconocido')
                            st.error(f"❌ Error al enviar email")
                            
                            # Mostrar error detallado
                            with st.expander("🔍 Ver detalle del error", expanded=True):
                                st.text(error_detail)
                                
                                # Sugerencias específicas según el tipo de error
                                if "timeout" in error_detail.lower() or "10060" in error_detail.lower():
                                    st.warning("""
                                    **💡 Sugerencias para error de timeout/conexión:**
                                    1. Ve a la pestaña "🤖 Configurar Agente" y usa el botón "🔍 Probar Conexión"
                                    2. Verifica que el servidor y puerto sean correctos
                                    3. Desactiva temporalmente tu firewall/antivirus
                                    4. Verifica tu conexión a internet
                                    5. Prueba con otro proveedor SMTP
                                    """)
                                elif "authentication" in error_detail.lower() or "autenticación" in error_detail.lower():
                                    st.warning("""
                                    **💡 Sugerencias para error de autenticación:**
                                    1. Para Gmail/Yahoo: Usa un App Password, NO tu contraseña normal
                                    2. Gmail: https://myaccount.google.com/apppasswords
                                    3. Yahoo: https://login.yahoo.com/account/security
                                    4. Verifica que el email sea correcto
                                    """)
                                else:
                                    st.info("💡 Revisa la sección '🆘 Ayuda y Troubleshooting' arriba para más información")
        else:
            st.error(f"❌ Error al cargar agentes: {agents_data.get('detail', 'Error desconocido')}")
    
    # ==================== SUB-TAB 2: Proveedores SMTP ====================
    with tab_email[1]:
        st.subheader("⚙️ Proveedores SMTP Predefinidos")
        st.markdown("Configuraciones listas para usar de los proveedores más comunes.")
        
        with st.spinner("Cargando proveedores..."):
            success, providers_data = api_request("GET", "/email/providers")
        
        if success:
            providers = providers_data.get("providers", {})
            
            for provider_name, config in providers.items():
                with st.expander(f"📧 {provider_name.upper()}", expanded=(provider_name == "gmail")):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Servidor:** `{config['server']}`")
                        st.write(f"**Puerto:** `{config['port']}`")
                        st.write(f"**TLS:** {'✅ Sí' if config.get('use_tls') else '❌ No'}")
                    
                    with col2:
                        st.info(f"ℹ️ {config.get('instructions', 'Sin instrucciones')}")
                    
                    # Código de ejemplo
                    st.markdown("**Configuración de ejemplo:**")
                    st.code(json.dumps({
                        "server": config['server'],
                        "port": config['port'],
                        "email": f"tu_email@{provider_name}.com",
                        "password": "tu_app_password",
                        "use_tls": config.get('use_tls', True)
                    }, indent=2), language="json")
        else:
            st.error(f"❌ Error al cargar proveedores: {providers_data.get('detail')}")
    
    # ==================== SUB-TAB 3: Configurar Agente ====================
    with tab_email[2]:
        st.subheader("🤖 Configurar SMTP en un Agente")
        st.markdown("Asigna credenciales SMTP a un agente para que pueda enviar emails.")
        
        # Listar todos los agentes
        success_agents, agents_data = api_request("GET", "/agents")
        
        if success_agents:
            agents = agents_data.get("agents", [])
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                selected_agent_id = st.selectbox(
                    "Selecciona el agente:",
                    options=[a["id"] for a in agents],
                    format_func=lambda x: f"{next((a['name'] for a in agents if a['id'] == x), x)} ({x})"
                )
            
            with col2:
                quick_provider = st.selectbox(
                    "Plantilla rápida:",
                    options=["", "gmail", "outlook", "yahoo", "office365", "custom"],
                    format_func=lambda x: {
                        "": "Seleccionar...",
                        "gmail": "📧 Gmail",
                        "outlook": "📧 Outlook",
                        "yahoo": "📧 Yahoo",
                        "office365": "📧 Office 365",
                        "custom": "⚙️ Personalizado"
                    }.get(x, x)
                )
            
            # Prellenar según plantilla
            if quick_provider and quick_provider != "custom":
                success_prov, prov_data = api_request("GET", "/email/providers")
                if success_prov:
                    provider_config = prov_data.get("providers", {}).get(quick_provider, {})
                    default_server = provider_config.get("server", "")
                    default_port = provider_config.get("port", 587)
                    default_tls = provider_config.get("use_tls", True)
                else:
                    default_server, default_port, default_tls = "", 587, True
            else:
                default_server, default_port, default_tls = "", 587, True
            
            st.markdown("---")
            st.markdown("##### Configuración SMTP")
            
            col_smtp1, col_smtp2 = st.columns(2)
            
            with col_smtp1:
                smtp_server = st.text_input(
                    "Servidor SMTP:",
                    value=default_server,
                    placeholder="smtp.gmail.com",
                    help="Dirección del servidor SMTP"
                )
                
                smtp_email = st.text_input(
                    "Email del remitente:",
                    placeholder="bot@gmail.com",
                    help="Email que aparecerá como remitente"
                )
            
            with col_smtp2:
                smtp_port = st.number_input(
                    "Puerto:",
                    min_value=1,
                    max_value=65535,
                    value=default_port,
                    help="587 para TLS, 465 para SSL"
                )
                
                smtp_password = st.text_input(
                    "Password:",
                    type="password",
                    placeholder="App Password o contraseña",
                    help="Para Gmail/Yahoo usa App Password"
                )
            
            smtp_use_tls = st.checkbox("Usar TLS", value=default_tls, help="Puerto 587")
            smtp_use_ssl = st.checkbox("Usar SSL", value=False, help="Puerto 465")
            
            st.markdown("---")
            
            col_btn1, col_btn2 = st.columns(2)
            
            with col_btn1:
                if st.button("🔍 Probar Conexión", use_container_width=True, help="Verifica si puedes conectarte al servidor SMTP"):
                    if not smtp_server or not smtp_port:
                        st.error("⚠️ Completa servidor y puerto para probar la conexión")
                    else:
                        import socket
                        with st.spinner(f"Probando conexión a {smtp_server}:{smtp_port}..."):
                            try:
                                # Probar conexión al puerto
                                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                                sock.settimeout(5)
                                result = sock.connect_ex((smtp_server, smtp_port))
                                sock.close()
                                
                                if result == 0:
                                    st.success(f"✅ Conexión exitosa a {smtp_server}:{smtp_port}")
                                    st.info("💡 El servidor está accesible. Puedes guardar la configuración.")
                                else:
                                    st.error(f"❌ No se puede conectar al servidor\n\nVerifica:\n- Servidor correcto\n- Puerto abierto\n- Firewall/antivirus")
                            except socket.timeout:
                                st.error(f"⏱️ Timeout: El servidor no responde\n\nPosibles causas:\n- Firewall bloqueando\n- Servidor incorrecto\n- Problemas de red")
                            except Exception as e:
                                st.error(f"❌ Error: {str(e)}\n\nVerifica tu configuración de red")
            
            with col_btn2:
                if st.button("💾 Guardar Configuración", type="primary", use_container_width=True):
                    if not smtp_server or not smtp_email or not smtp_password:
                        st.error("⚠️ Completa todos los campos obligatorios")
                    else:
                        smtp_config = {
                            "server": smtp_server,
                            "port": smtp_port,
                            "email": smtp_email,
                            "password": smtp_password,
                            "use_tls": smtp_use_tls,
                            "use_ssl": smtp_use_ssl
                        }
                        
                        update_data = {"smtp_config": smtp_config}
                        
                        with st.spinner("Guardando configuración..."):
                            success, result = api_request("PUT", f"/agents/{selected_agent_id}", data=update_data)
                        
                        if success:
                            st.success("✅ Configuración SMTP guardada exitosamente")
                            st.rerun()
                        else:
                            st.error(f"❌ Error: {result.get('detail', 'Error desconocido')}")
            
            # Mostrar configuración actual
            selected_agent = next((a for a in agents if a["id"] == selected_agent_id), None)
            if selected_agent and selected_agent.get("smtp_config"):
                st.markdown("---")
                st.markdown("##### Configuración Actual")
                smtp_current = selected_agent.get("smtp_config", {})
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Servidor", smtp_current.get("server", "N/A"))
                col2.metric("Puerto", smtp_current.get("port", "N/A"))
                col3.metric("Email", smtp_current.get("email", "N/A"))
                
                with st.expander("Ver configuración completa (JSON)"):
                    display_config = smtp_current.copy()
                    if "password" in display_config:
                        display_config["password"] = "***" * 5
                    st.json(display_config)
        else:
            st.error(f"❌ Error al cargar agentes: {agents_data.get('detail')}")
    
    # ==================== SUB-TAB 4: Historial ====================
    with tab_email[3]:
        st.subheader("📊 Historial de Emails Enviados")
        st.markdown("Registro de emails enviados por tus agentes (requiere MCP SQLite habilitado).")
        
        # Listar agentes con SMTP
        success_agents, agents_data = api_request("GET", "/agents")
        
        if success_agents:
            agents = agents_data.get("agents", [])
            agents_with_smtp = [a for a in agents if a.get("smtp_config")]
            
            if not agents_with_smtp:
                st.info("ℹ️ No hay agentes con configuración SMTP")
            else:
                selected_agent_id = st.selectbox(
                    "Filtrar por agente:",
                    options=["all"] + [a["id"] for a in agents_with_smtp],
                    format_func=lambda x: "Todos los agentes" if x == "all" else next((a["name"] for a in agents_with_smtp if a["id"] == x), x)
                )
                
                if selected_agent_id == "all":
                    st.info("ℹ️ Mostrando historial de todos los agentes con SMTP")
                else:
                    # Consultar logs de ese agente
                    query_data = {
                        "query": "SELECT * FROM agent_logs WHERE action = 'email_sent' ORDER BY timestamp DESC LIMIT 50"
                    }
                    
                    with st.spinner("Consultando historial..."):
                        success, result = api_request("POST", f"/mcp/agents/{selected_agent_id}/query", data=query_data)
                    
                    if success:
                        rows = result.get("rows", [])
                        
                        st.metric("Total de emails enviados", result.get("count", 0))
                        
                        if rows:
                            st.markdown("---")
                            
                            for idx, row in enumerate(rows):
                                with st.expander(f"📧 {row.get('timestamp', 'N/A')} - ID: {row.get('id')}"):
                                    col1, col2 = st.columns(2)
                                    
                                    with col1:
                                        st.write(f"**Session ID:** {row.get('session_id', 'N/A')}")
                                        st.write(f"**Éxito:** {'✅ Sí' if row.get('success') else '❌ No'}")
                                    
                                    with col2:
                                        st.write(f"**Timestamp:** {row.get('timestamp', 'N/A')}")
                                    
                                    if row.get('details'):
                                        try:
                                            details = json.loads(row.get('details', '{}'))
                                            st.markdown("**Detalles:**")
                                            st.json(details)
                                        except:
                                            st.text(row.get('details', ''))
                        else:
                            st.info("ℹ️ No hay emails enviados registrados para este agente")
                    else:
                        st.error(f"❌ Error al consultar historial: {result.get('detail', 'Error desconocido')}")

# ============================================================================
# TAB 7: Sesiones
# ============================================================================

with tabs[6]:
    st.header("📝 Gestión de Sesiones")
    
    # Filtro por agente
    col_filter1, col_filter2 = st.columns([2, 1])
    
    with col_filter1:
        filter_options = ["Todas las sesiones"]
        success, agents_data = api_request("GET", "/agents")
        if success and agents_data.get("agents"):
            filter_options.extend([f"{a['name']} ({a['id']})" for a in agents_data["agents"]])
        
        filter_selection = st.selectbox("🔍 Filtrar por Agente", filter_options)
    
    with col_filter2:
        if st.button("🔄 Actualizar Lista", use_container_width=True):
            st.rerun()
    
    # Obtener sesiones
    filter_agent_id = None
    if filter_selection != "Todas las sesiones":
        filter_agent_id = filter_selection.split("(")[-1].strip(")")
    
    params = {"agent_id": filter_agent_id} if filter_agent_id else None
    success, sessions_data = api_request("GET", "/sessions", params=params)
    
    if success and sessions_data.get("sessions"):
        st.info(f"📊 Total de sesiones: {sessions_data['count']}")
        
        for session in sessions_data["sessions"]:
            agent_id = session["agent_id"]
            session_id = session["session_id"]
            message_count = session.get("message_count", 0)
            
            with st.expander(f"**{agent_id}** / {session_id} - {message_count} mensajes"):
                col_a, col_b = st.columns([3, 1])
                
                with col_a:
                    # Botón para ver historial
                    if st.button(f"👁️ Ver Historial", key=f"view_{agent_id}_{session_id}"):
                        success_hist, hist_data = api_request("GET", f"/sessions/{agent_id}/{session_id}")
                        if success_hist:
                            st.json(hist_data)
                
                with col_b:
                    # Botón para eliminar sesión
                    if st.button(f"🗑️ Eliminar", key=f"del_{agent_id}_{session_id}", type="secondary"):
                        success_del, result = api_request("DELETE", f"/sessions/{agent_id}/{session_id}")
                        if success_del:
                            st.success("✅ Sesión eliminada")
                            st.rerun()
    else:
        st.info("No hay sesiones activas.")

# ============================================================================
# TAB 8: ChromaDB Admin
# ============================================================================

with tabs[7]:
    st.header("🗄️ Administración de ChromaDB")
    
    st.info("💡 Esta sección permite administrar las colecciones de ChromaDB a bajo nivel.")
    
    # Estadísticas generales
    success, collections_data = api_request("GET", "/chromadb/collections")
    
    if success:
        st.subheader("📊 Estadísticas de ChromaDB")
        
        total_collections = collections_data.get("count", 0)
        st.metric("📚 Total de Colecciones", total_collections)
        
        st.markdown("---")
        st.subheader("📋 Colecciones Disponibles")
        
        for collection_detail in collections_data.get("details", []):
            collection_name = collection_detail["name"]
            metadata = collection_detail.get("metadata")
            
            with st.expander(f"**{collection_name}**"):
                st.write("**Metadata:**")
                if metadata is not None and metadata != "NULL":
                    st.json(metadata if metadata else {})
                else:
                    st.info("Sin metadata")
                
                col_act1, col_act2, col_act3 = st.columns(3)
                
                with col_act1:
                    if st.button(f"📊 Ver Info Detallada", key=f"info_{collection_name}"):
                        success_info, info_data = api_request("GET", f"/chromadb/collections/{collection_name}")
                        if success_info:
                            st.json(info_data)
                
                with col_act2:
                    if st.button(f"👁️ Preview Docs", key=f"peek_{collection_name}"):
                        success_peek, peek_data = api_request("GET", f"/chromadb/collections/{collection_name}/peek")
                        if success_peek:
                            st.json(peek_data)
                
                with col_act3:
                    if collection_name != "kb_store":
                        if st.button(f"🗑️ Eliminar", key=f"delete_col_{collection_name}", type="secondary"):
                            st.session_state[f"confirm_delete_col_{collection_name}"] = True
                
                # Confirmar eliminación
                if st.session_state.get(f"confirm_delete_col_{collection_name}", False):
                    st.warning(f"⚠️ ¿Eliminar colección '{collection_name}'?")
                    col_yes, col_no = st.columns(2)
                    with col_yes:
                        if st.button("✅ Sí", key=f"yes_{collection_name}"):
                            success_del, result = api_request("DELETE", f"/chromadb/collections/{collection_name}")
                            if success_del:
                                st.success("✅ Colección eliminada")
                                st.rerun()
                    with col_no:
                        if st.button("❌ No", key=f"no_{collection_name}"):
                            st.session_state[f"confirm_delete_col_{collection_name}"] = False
                            st.rerun()

# ============================================================================
# TAB 9: Modelos Ollama
# ============================================================================

with tabs[8]:
    st.header("🔧 Gestión de Modelos Ollama")
    st.markdown("Administra los modelos LLM disponibles, cambia entre ellos y descarga nuevos modelos.")
    
    # Obtener modelos actuales
    success_current, current_data = api_request("GET", "/ollama/models/current")
    
    if success_current:
        st.info(f"**Modelo Chat Actual:** `{current_data.get('chat_model')}` | "
                f"**Modelo Embeddings Actual:** `{current_data.get('embed_model')}`")
    
    st.markdown("---")
    
    # Crear dos columnas principales
    col_models, col_actions = st.columns([1.5, 1])
    
    # ========================================================================
    # Columna izquierda: Lista de modelos
    # ========================================================================
    with col_models:
        st.subheader("📦 Modelos Instalados")
        
        if st.button("🔄 Refrescar Lista", key="refresh_ollama_models", use_container_width=True):
            st.rerun()
        
        success_list, models_data = api_request("GET", "/ollama/models")
        
        if success_list:
            models = models_data.get("models", [])
            current_chat = models_data.get("current_chat_model")
            current_embed = models_data.get("current_embed_model")
            
            if models:
                st.success(f"✅ {len(models)} modelos disponibles")
                
                # Mostrar cada modelo
                for idx, model in enumerate(models):
                    model_name = model.get("name", "Unknown")
                    model_size = model.get("size", 0)
                    size_gb = model_size / (1024**3)
                    
                    # Determinar si es el modelo actual
                    is_current_chat = model_name.startswith(current_chat)
                    is_current_embed = model_name.startswith(current_embed)
                    
                    badge = ""
                    if is_current_chat:
                        badge = "💬 **CHAT ACTIVO**"
                    elif is_current_embed:
                        badge = "🔤 **EMBED ACTIVO**"
                    
                    with st.expander(f"**{model_name}** - {size_gb:.2f} GB {badge}", 
                                   expanded=False):
                        st.write(f"**Tamaño:** {size_gb:.2f} GB ({model_size:,} bytes)")
                        st.write(f"**Modificado:** {model.get('modified', 'N/A')}")
                        st.write(f"**Digest:** `{model.get('digest', 'N/A')}`")
                        
                        # Botones de acción
                        col_btn1, col_btn2, col_btn3 = st.columns(3)
                        
                        with col_btn1:
                            if st.button("💬 Usar como Chat", key=f"chat_{idx}"):
                                # Extraer el nombre base del modelo (sin :tag)
                                base_name = model_name.split(':')[0]
                                success_sel, result = api_request("POST", "/ollama/models/select", 
                                    data={"model_name": base_name, "model_type": "chat"})
                                if success_sel:
                                    st.success(f"✅ Modelo de chat cambiado a: {base_name}")
                                    st.rerun()
                                else:
                                    st.error(f"❌ Error: {result.get('error')}")
                        
                        with col_btn2:
                            if st.button("🔤 Usar como Embed", key=f"embed_{idx}"):
                                base_name = model_name.split(':')[0]
                                success_sel, result = api_request("POST", "/ollama/models/select",
                                    data={"model_name": base_name, "model_type": "embed"})
                                if success_sel:
                                    st.success(f"✅ Modelo de embeddings cambiado a: {base_name}")
                                    st.rerun()
                                else:
                                    st.error(f"❌ Error: {result.get('error')}")
                        
                        with col_btn3:
                            if st.button("ℹ️ Ver Info", key=f"info_{idx}"):
                                base_name = model_name.split(':')[0]
                                success_info, info_data = api_request("GET", f"/ollama/models/{base_name}")
                                if success_info:
                                    st.json(info_data.get("info", {}))
                                else:
                                    st.error("No se pudo obtener información del modelo")
            else:
                st.warning("⚠️ No hay modelos instalados")
        else:
            st.error(f"❌ Error al listar modelos: {models_data.get('error')}")
    
    # ========================================================================
    # Columna derecha: Acciones
    # ========================================================================
    with col_actions:
        st.subheader("⚙️ Acciones")
        
        # Cambiar modelo manualmente
        st.markdown("#### 🔄 Cambiar Modelo")
        with st.form("change_model_form"):
            model_name_input = st.text_input(
                "Nombre del Modelo",
                placeholder="llama3.1",
                help="Nombre del modelo (sin :tag)"
            )
            model_type = st.selectbox(
                "Tipo de Modelo",
                ["chat", "embed"],
                help="Selecciona el tipo de modelo"
            )
            
            if st.form_submit_button("🔄 Cambiar Modelo", use_container_width=True):
                if model_name_input:
                    success_change, result = api_request("POST", "/ollama/models/select",
                        data={"model_name": model_name_input, "model_type": model_type})
                    if success_change:
                        st.success(f"✅ {result.get('message')}")
                        st.rerun()
                    else:
                        st.error(f"❌ {result.get('error')}")
                else:
                    st.warning("⚠️ Ingresa el nombre del modelo")
        
        st.markdown("---")
        
        # Descargar nuevo modelo
        st.markdown("#### ⬇️ Descargar Modelo")
        
        # Modelos populares como sugerencias
        popular_models = [
            "llama3.1", "llama3.2", "llama3", 
            "mistral", "mixtral", "codellama",
            "gemma", "qwen2.5", "phi3",
            "nomic-embed-text"
        ]
        
        # Radio button FUERA del formulario para que sea interactivo
        download_option = st.radio(
            "Selecciona opción",
            ["Popular", "Personalizado"],
            horizontal=True
        )
        
        with st.form("download_model_form"):
            if download_option == "Popular":
                model_to_download = st.selectbox(
                    "Modelos Populares",
                    popular_models,
                    help="Selecciona un modelo popular"
                )
            else:
                model_to_download = st.text_input(
                    "Nombre del Modelo",
                    placeholder="model-name:tag",
                    help="Ej: llama3.1:latest o mistral:7b"
                )
            
            if st.form_submit_button("⬇️ Descargar", type="primary", use_container_width=True):
                if model_to_download:
                    progress_placeholder = st.empty()
                    status_placeholder = st.empty()
                    
                    progress_placeholder.info(f"📥 Iniciando descarga de **{model_to_download}**...")
                    
                    try:
                        # Hacer request de descarga
                        url = f"{API_BASE_URL}/ollama/models/download"
                        response = requests.post(
                            url, 
                            json={"model_name": model_to_download},
                            stream=True,
                            timeout=1800  # 30 minutos timeout
                        )
                        
                        if response.status_code == 200:
                            progress_bar = st.progress(0)
                            last_status = ""
                            
                            for line in response.iter_lines():
                                if line:
                                    try:
                                        data = json.loads(line.decode('utf-8'))
                                        status = data.get("status", "")
                                        
                                        if status == "completed":
                                            progress_bar.progress(100)
                                            status_placeholder.success(f"✅ {data.get('message')}")
                                            st.balloons()
                                            break
                                        elif status == "error":
                                            status_placeholder.error(f"❌ {data.get('message')}")
                                            break
                                        elif status == "downloading":
                                            # Calcular progreso
                                            total = data.get("total", 1)
                                            completed = data.get("completed", 0)
                                            percent = int((completed / total) * 100) if total > 0 else 0
                                            progress_bar.progress(min(percent, 100))
                                            status_placeholder.info(f"📥 Descargando: {percent}%")
                                        else:
                                            status_placeholder.info(f"📥 {status}")
                                            last_status = status
                                    except:
                                        pass
                            
                            # Esperar 2 segundos y recargar
                            import time
                            time.sleep(2)
                            st.rerun()
                        else:
                            status_placeholder.error(f"❌ Error: {response.text}")
                    except Exception as e:
                        status_placeholder.error(f"❌ Error: {str(e)}")
                else:
                    st.warning("⚠️ Ingresa el nombre del modelo")
        
        st.markdown("---")
        
        # Información útil
        with st.expander("ℹ️ Ayuda - Modelos Populares"):
            st.markdown("""
            **Modelos de Chat:**
            - `llama3.1` - Recomendado, última versión
            - `mistral` - Rápido y eficiente
            - `codellama` - Especializado en código
            - `gemma` - Modelo de Google
            
            **Modelos de Embeddings:**
            - `nomic-embed-text` - Recomendado
            - `all-minilm` - Ligero y rápido
            
            **Más modelos:** https://ollama.ai/library
            """)

# ============================================================================
# TAB 10: Gestión de Categorías de Modelos
# ============================================================================

with tabs[9]:
    st.header("🏷️ Gestión de Categorías de Modelos")
    st.markdown("Asigna categorías personalizadas a tus modelos LLM para organizarlos mejor.")
    
    # Cargar configuración actual
    config = load_model_categories()
    categories_config = config.get("categories", {})
    
    # Obtener modelos disponibles de Ollama
    success_models, models_data = api_request("GET", "/ollama/models")
    available_models = []
    if success_models:
        models = models_data.get("models", [])
        available_models = sorted([m.get("name", "") for m in models if m.get("name")])
    
    st.markdown("---")
    
    # Sección 1: Ver categorización actual
    st.subheader("📊 Categorización Actual")
    
    if available_models:
        categorized = categorize_models(available_models)
        
        col_stats1, col_stats2, col_stats3 = st.columns(3)
        col_stats1.metric("📦 Total de Modelos", len(available_models))
        col_stats2.metric("🏷️ Categorías Usadas", len(categorized))
        col_stats3.metric("⚙️ Categorías Configuradas", len(categories_config))
        
        st.markdown("---")
        
        # Mostrar modelos por categoría
        for category, models_in_cat in categorized.items():
            with st.expander(f"{category} ({len(models_in_cat)} modelos)", expanded=False):
                # Obtener descripción de la categoría
                cat_description = categories_config.get(category, {}).get("description", "Sin descripción")
                if cat_description:
                    st.info(f"📝 {cat_description}")
                
                # Mostrar modelos en columnas
                cols = st.columns(3)
                for idx, model in enumerate(models_in_cat):
                    with cols[idx % 3]:
                        st.caption(f"• {model}")
    else:
        st.warning("⚠️ No hay modelos disponibles en Ollama")
    
    st.markdown("---")
    
    # Sección 2: Asignar modelo a categoría
    st.subheader("🎯 Asignar Modelo a Categoría")
    
    col_assign1, col_assign2 = st.columns([1, 1])
    
    with col_assign1:
        if available_models:
            # Mostrar categoría actual de cada modelo
            st.markdown("##### Selecciona un modelo:")
            selected_model = st.selectbox(
                "Modelo:",
                options=available_models,
                key="model_to_categorize",
                label_visibility="collapsed"
            )
            
            if selected_model:
                current_category = get_model_category(selected_model, config)
                st.success(f"**Categoría actual:** {current_category}")
    
    with col_assign2:
        if available_models and selected_model:
            st.markdown("##### Asignar a nueva categoría:")
            
            # Obtener lista de categorías disponibles
            available_categories = list(categories_config.keys())
            if not available_categories:
                available_categories = [
                    "💬 Chatbot / Conversacional",
                    "💻 Desarrollo / Código",
                    "🧠 Razonamiento / Análisis",
                    "🌍 Multilingüe",
                    "📊 Embeddings",
                    "⚡ Rápidos / Ligeros",
                    "🎯 Especializados",
                    "🔧 Otros"
                ]
            
            new_category = st.selectbox(
                "Nueva categoría:",
                options=available_categories,
                key="new_category",
                label_visibility="collapsed"
            )
            
            if st.button("💾 Asignar Categoría", type="primary", use_container_width=True):
                if assign_model_to_category(selected_model, new_category):
                    st.success(f"✅ Modelo '{selected_model}' asignado a '{new_category}'")
                    st.rerun()
                else:
                    st.error("❌ Error al asignar categoría")
    
    st.markdown("---")
    
    # Sección 3: Gestionar categorías
    st.subheader("⚙️ Gestionar Categorías")
    
    col_manage1, col_manage2 = st.columns([1, 1])
    
    with col_manage1:
        st.markdown("##### Agregar Nueva Categoría")
        
        with st.form("add_category_form"):
            new_cat_icon = st.text_input(
                "Emoji/Icono:",
                placeholder="🎨",
                max_chars=2
            )
            new_cat_name = st.text_input(
                "Nombre de Categoría:",
                placeholder="Arte / Diseño"
            )
            new_cat_desc = st.text_area(
                "Descripción:",
                placeholder="Modelos especializados en arte y diseño",
                height=80
            )
            
            if st.form_submit_button("➕ Agregar Categoría", use_container_width=True):
                if new_cat_icon and new_cat_name:
                    full_cat_name = f"{new_cat_icon} {new_cat_name}"
                    
                    if full_cat_name not in categories_config:
                        config["categories"][full_cat_name] = {
                            "description": new_cat_desc,
                            "models": [],
                            "patterns": []
                        }
                        
                        if save_model_categories(config):
                            st.success(f"✅ Categoría '{full_cat_name}' creada")
                            st.rerun()
                        else:
                            st.error("❌ Error al crear categoría")
                    else:
                        st.warning("⚠️ Esta categoría ya existe")
                else:
                    st.error("⚠️ Completa al menos el icono y el nombre")
    
    with col_manage2:
        st.markdown("##### Editar Patrones de Categoría")
        
        if categories_config:
            selected_cat = st.selectbox(
                "Categoría a editar:",
                options=list(categories_config.keys()),
                key="category_to_edit"
            )
            
            if selected_cat:
                current_patterns = categories_config[selected_cat].get("patterns", [])
                
                st.caption(f"Patrones actuales: {', '.join(current_patterns) if current_patterns else 'Ninguno'}")
                
                new_patterns = st.text_input(
                    "Patrones (separados por coma):",
                    value=", ".join(current_patterns),
                    placeholder="pattern1, pattern2, pattern3",
                    help="Estos patrones se usarán para categorizar automáticamente nuevos modelos"
                )
                
                if st.button("💾 Actualizar Patrones", use_container_width=True):
                    patterns_list = [p.strip() for p in new_patterns.split(",") if p.strip()]
                    config["categories"][selected_cat]["patterns"] = patterns_list
                    
                    if save_model_categories(config):
                        st.success(f"✅ Patrones actualizados para '{selected_cat}'")
                        st.rerun()
                    else:
                        st.error("❌ Error al actualizar patrones")
    
    st.markdown("---")
    
    # Sección 4: Información del archivo de configuración
    with st.expander("ℹ️ Información de Configuración", expanded=False):
        st.markdown(f"**Archivo:** `{CATEGORIES_FILE}`")
        
        if "_metadata" in config:
            metadata = config["_metadata"]
            st.write(f"**Versión:** {metadata.get('version', 'N/A')}")
            st.write(f"**Última actualización:** {metadata.get('last_updated', 'N/A')}")
        
        st.markdown("**Configuración actual (JSON):**")
        st.json(config)
        
        if st.button("🔄 Recargar Configuración desde Archivo"):
            st.rerun()

# ============================================================================
# Footer
# ============================================================================

st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray;'>
        🤖 RAG Ollama API Manager | Construido con Streamlit<br>
        API Base URL: <code>http://localhost:8000</code>
    </div>
    """,
    unsafe_allow_html=True
)
