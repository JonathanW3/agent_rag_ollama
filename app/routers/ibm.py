from fastapi import APIRouter, HTTPException, Query
from ..schemas import IBMQueryRequest
from mcp_mysql_ibm.client import get_ibm_client

router = APIRouter(prefix="/ibm", tags=["🏢 MySQL IBM"])


@router.get("/schema", summary="Esquema de la BD ibm")
async def ibm_schema():
    """Retorna el esquema completo de la base de datos ibm (tablas y columnas)."""
    try:
        client = get_ibm_client()
        return await client.get_schema()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tables", summary="Listar tablas")
async def ibm_tables():
    """Lista todas las tablas disponibles en ibm con su conteo de filas."""
    try:
        client = get_ibm_client()
        return await client.list_tables()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query", summary="Consulta SELECT libre")
async def ibm_query(request: IBMQueryRequest):
    """Ejecuta cualquier SELECT en la base de datos ibm. Solo lectura."""
    try:
        client = get_ibm_client()
        return await client.query(request.query, request.params or None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════
# Credit Cards
# ══════════════════════════════════════════════════════════════════════════

@router.get("/tarjetas", summary="Buscar tarjetas de crédito")
async def ibm_buscar_tarjeta(
    titular: str = Query(default="", description="Nombre del titular"),
    banco: str = Query(default="", description="Banco emisor"),
    tipo: str = Query(default="", description="Tipo: VI, AX, MC, etc."),
    limit: int = Query(default=20, ge=1, le=200)
):
    """Busca tarjetas de crédito por titular, banco emisor o tipo."""
    try:
        client = get_ibm_client()
        return await client.buscar_tarjeta(titular, banco, tipo, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tarjetas/resumen", summary="Resumen tarjetas por banco o tipo")
async def ibm_resumen_tarjetas(
    agrupar_por: str = Query(default="banco", description="banco | tipo")
):
    """Resumen estadístico de tarjetas agrupado por banco o tipo."""
    try:
        client = get_ibm_client()
        return await client.resumen_tarjetas(agrupar_por)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════
# Bank Transactions
# ══════════════════════════════════════════════════════════════════════════

@router.get("/transacciones", summary="Buscar transacciones bancarias")
async def ibm_buscar_transaccion(
    descripcion: str = Query(default="", description="Texto en descripción"),
    fecha_desde: str = Query(default="", description="YYYY-MM-DD"),
    fecha_hasta: str = Query(default="", description="YYYY-MM-DD"),
    tipo: str = Query(default="todos", description="deposito | retiro | todos"),
    limit: int = Query(default=50, ge=1, le=500)
):
    """Busca transacciones bancarias con filtros opcionales."""
    try:
        client = get_ibm_client()
        return await client.buscar_transaccion(descripcion, fecha_desde, fecha_hasta, tipo, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/transacciones/resumen", summary="Resumen de transacciones")
async def ibm_resumen_transacciones(
    fecha_desde: str = Query(default="", description="YYYY-MM-DD"),
    fecha_hasta: str = Query(default="", description="YYYY-MM-DD")
):
    """Resumen: total depósitos, retiros y balance."""
    try:
        client = get_ibm_client()
        return await client.resumen_transacciones(fecha_desde, fecha_hasta)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════
# Employees
# ══════════════════════════════════════════════════════════════════════════

@router.get("/empleados", summary="Buscar empleados")
async def ibm_buscar_empleado(
    nombre: str = Query(default="", description="Nombre o apellido"),
    estado: str = Query(default="", description="State (OH, DC, CA, etc.)"),
    ciudad: str = Query(default="", description="Ciudad"),
    salario_min: float = Query(default=None, description="Salario mínimo"),
    salario_max: float = Query(default=None, description="Salario máximo"),
    limit: int = Query(default=20, ge=1, le=200)
):
    """Busca empleados por nombre, ubicación o rango salarial."""
    try:
        client = get_ibm_client()
        return await client.buscar_empleado(nombre, estado, ciudad, salario_min, salario_max, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/empleados/resumen", summary="Resumen de empleados")
async def ibm_resumen_empleados(
    agrupar_por: str = Query(default="region", description="estado | region | genero"),
    limit: int = Query(default=20, ge=1, le=100)
):
    """Estadísticas de empleados agrupadas por estado, región o género."""
    try:
        client = get_ibm_client()
        return await client.resumen_empleados(agrupar_por, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════
# HR Attrition
# ══════════════════════════════════════════════════════════════════════════

@router.get("/attrition", summary="Análisis de attrition")
async def ibm_analisis_attrition(
    attrition: str = Query(default="todos", description="Yes | No | todos"),
    departamento: str = Query(default="", description="Departamento"),
    rol: str = Query(default="", description="JobRole"),
    overtime: str = Query(default="todos", description="Yes | No | todos"),
    limit: int = Query(default=50, ge=1, le=500)
):
    """Analiza la rotación de personal con filtros opcionales."""
    try:
        client = get_ibm_client()
        return await client.analisis_attrition(attrition, departamento, rol, overtime, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/attrition/resumen", summary="Attrition por departamento")
async def ibm_attrition_por_departamento(
    agrupar_por: str = Query(default="departamento", description="departamento | rol | overtime | estado_civil")
):
    """Resumen de attrition agrupado por departamento, rol, overtime o estado civil."""
    try:
        client = get_ibm_client()
        return await client.attrition_por_departamento(agrupar_por)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/attrition/factores", summary="Factores de attrition")
async def ibm_factores_attrition():
    """Compara factores clave entre empleados con y sin attrition."""
    try:
        client = get_ibm_client()
        return await client.factores_attrition()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════
# Sales Orders
# ══════════════════════════════════════════════════════════════════════════

@router.get("/ventas", summary="Buscar órdenes de venta")
async def ibm_buscar_orden(
    region: str = Query(default="", description="Región"),
    pais: str = Query(default="", description="País"),
    tipo_producto: str = Query(default="", description="Item Type"),
    canal: str = Query(default="todos", description="Online | Offline | todos"),
    fecha_desde: str = Query(default="", description="YYYY-MM-DD"),
    fecha_hasta: str = Query(default="", description="YYYY-MM-DD"),
    limit: int = Query(default=50, ge=1, le=500)
):
    """Busca órdenes de venta por región, país, producto, canal o fechas."""
    try:
        client = get_ibm_client()
        return await client.buscar_orden(region, pais, tipo_producto, canal, fecha_desde, fecha_hasta, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ventas/region", summary="Ventas por región")
async def ibm_ventas_por_region(
    agrupar_por: str = Query(default="region", description="region | pais | producto | canal | prioridad"),
    limit: int = Query(default=20, ge=1, le=100)
):
    """Resumen de ventas agrupado por región, país, producto, canal o prioridad."""
    try:
        client = get_ibm_client()
        return await client.ventas_por_region(agrupar_por, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ventas/top", summary="Top productos vendidos")
async def ibm_top_productos(
    region: str = Query(default="", description="Filtrar por región"),
    canal: str = Query(default="todos", description="Online | Offline | todos"),
    ordenar_por: str = Query(default="revenue", description="unidades | revenue | profit"),
    limit: int = Query(default=10, ge=1, le=100)
):
    """Ranking de productos por unidades, revenue o profit."""
    try:
        client = get_ibm_client()
        return await client.top_productos(region, canal, ordenar_por, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ventas/resumen", summary="KPIs generales de ventas")
async def ibm_resumen_ventas(
    region: str = Query(default="", description="Filtrar por región"),
    fecha_desde: str = Query(default="", description="YYYY-MM-DD"),
    fecha_hasta: str = Query(default="", description="YYYY-MM-DD")
):
    """KPIs generales: órdenes, unidades, revenue, costo, profit y margen."""
    try:
        client = get_ibm_client()
        return await client.resumen_ventas(region, fecha_desde, fecha_hasta)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
