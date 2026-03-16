from fastapi import APIRouter, HTTPException, Query
from ..schemas import MySQLQueryRequest
from mcp_mysql.client import get_mysql_client

router = APIRouter(prefix="/mysql", tags=["🏥 MySQL Farmacia"])


@router.get("/schema", summary="Esquema de farmacia_db")
async def mysql_schema():
    """Retorna el esquema completo de farmacia_db (tablas y columnas)."""
    try:
        client = get_mysql_client()
        return await client.get_schema()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query", summary="Consulta SELECT libre")
async def mysql_query(request: MySQLQueryRequest):
    """Ejecuta cualquier SELECT en farmacia_db. Solo lectura."""
    try:
        client = get_mysql_client()
        return await client.query(request.query, request.params or None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/medicamentos", summary="Buscar medicamentos")
async def mysql_buscar_medicamento(
    nombre: str = Query(default="", description="Nombre o parte del nombre"),
    laboratorio: str = Query(default="", description="Laboratorio"),
    clase: str = Query(default="", description="Clase terapéutica"),
    limit: int = Query(default=20, ge=1, le=200)
):
    """Busca medicamentos por nombre, laboratorio o clase terapéutica."""
    try:
        client = get_mysql_client()
        return await client.buscar_medicamento(nombre, laboratorio, clase, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock", summary="Verificar stock de medicamento")
async def mysql_verificar_stock(
    medicamento: str = Query(..., description="Nombre o parte del medicamento"),
    local_id: int = Query(default=None, description="ID del local (opcional)"),
    solo_disponibles: bool = Query(default=False, description="Excluir SIN STOCK")
):
    """Consulta el stock de un medicamento en todas o una farmacia."""
    try:
        client = get_mysql_client()
        return await client.verificar_stock(medicamento, local_id, solo_disponibles)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock/alertas", summary="Alertas de stock")
async def mysql_alertas_stock(
    local_id: int = Query(default=None, description="Filtrar por local (opcional)"),
    tipo: str = Query(default="TODOS", description="STOCK BAJO | SIN STOCK | TODOS"),
    limit: int = Query(default=50, ge=1, le=500)
):
    """Lista todos los registros con STOCK BAJO o SIN STOCK."""
    try:
        client = get_mysql_client()
        return await client.alertas_stock(local_id, tipo, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ventas", summary="Historial de ventas")
async def mysql_historial_ventas(
    local_id: int = Query(default=None, description="ID del local"),
    medicamento: str = Query(default="", description="Nombre del medicamento"),
    fecha_desde: str = Query(default="", description="YYYY-MM-DD"),
    fecha_hasta: str = Query(default="", description="YYYY-MM-DD"),
    metodo_pago: str = Query(default="", description="Método de pago"),
    limit: int = Query(default=50, ge=1, le=500)
):
    """Consulta el historial de compras con filtros opcionales."""
    try:
        client = get_mysql_client()
        return await client.historial_ventas(local_id, medicamento, fecha_desde, fecha_hasta, metodo_pago, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ventas/top", summary="Top medicamentos vendidos")
async def mysql_top_medicamentos(
    local_id: int = Query(default=None, description="Filtrar por local"),
    fecha_desde: str = Query(default="", description="YYYY-MM-DD"),
    fecha_hasta: str = Query(default="", description="YYYY-MM-DD"),
    ordenar_por: str = Query(default="cantidad", description="cantidad | ingresos"),
    limit: int = Query(default=10, ge=1, le=100)
):
    """Ranking de medicamentos por cantidad vendida o ingresos generados."""
    try:
        client = get_mysql_client()
        return await client.top_medicamentos(local_id, fecha_desde, fecha_hasta, ordenar_por, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/farmacias/resumen", summary="Resumen KPIs por farmacia")
async def mysql_resumen_farmacia(
    local_id: int = Query(default=None, description="ID del local (opcional, si se omite retorna todos)")
):
    """KPIs por farmacia: ventas totales, ingresos, alertas de stock activas."""
    try:
        client = get_mysql_client()
        return await client.resumen_farmacia(local_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/usuarios", summary="Buscar clientes")
async def mysql_buscar_usuario(
    nombre: str = Query(default="", description="Nombre del cliente"),
    condicion: str = Query(default="", description="Condición crónica"),
    plan_salud: str = Query(default="", description="Plan de salud"),
    tipo_cliente: str = Query(default="", description="Tipo de cliente"),
    limit: int = Query(default=20, ge=1, le=200)
):
    """Busca clientes/usuarios en farmacia_db."""
    try:
        client = get_mysql_client()
        return await client.buscar_usuario(nombre, condicion, plan_salud, tipo_cliente, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
