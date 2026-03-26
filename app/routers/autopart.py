from fastapi import APIRouter, HTTPException, Query
from ..schemas import AutopartQueryRequest
from mcp_mysql_autopart.client import get_autopart_client

router = APIRouter(prefix="/autopart", tags=["🚗 MySQL Autopart"])


@router.get("/schema", summary="Esquema de la BD autopart")
async def autopart_schema():
    """Retorna el esquema completo de la base de datos autopart (tablas y columnas)."""
    try:
        client = get_autopart_client()
        return await client.get_schema()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tables", summary="Listar tablas")
async def autopart_tables():
    """Lista todas las tablas disponibles en autopart con su conteo de filas."""
    try:
        client = get_autopart_client()
        return await client.list_tables()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query", summary="Consulta SELECT libre")
async def autopart_query(request: AutopartQueryRequest):
    """Ejecuta cualquier SELECT en la base de datos autopart. Solo lectura."""
    try:
        client = get_autopart_client()
        return await client.query(request.query, request.params or None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════
# Vehicles
# ══════════════════════════════════════════════════════════════════════════

@router.get("/vehiculos", summary="Buscar vehículos")
async def autopart_buscar_vehiculo(
    modelo: str = Query(default="", description="Nombre del modelo"),
    fabricante: str = Query(default="", description="Fabricante/manufacturer"),
    tipo_vehiculo: str = Query(default="", description="Tipo de vehículo"),
    limit: int = Query(default=20, ge=1, le=200)
):
    """Busca vehículos por modelo, fabricante o tipo."""
    try:
        client = get_autopart_client()
        return await client.buscar_vehiculo(modelo, fabricante, tipo_vehiculo, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vehiculos/resumen", summary="Resumen de vehículos")
async def autopart_resumen_vehiculos(
    agrupar_por: str = Query(default="fabricante", description="fabricante | tipo"),
    limit: int = Query(default=20, ge=1, le=100)
):
    """Resumen de vehículos agrupado por fabricante o tipo."""
    try:
        client = get_autopart_client()
        return await client.resumen_vehiculos(agrupar_por, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════
# Product Category
# ══════════════════════════════════════════════════════════════════════════

@router.get("/categorias", summary="Buscar categorías")
async def autopart_buscar_categoria(
    nombre: str = Query(default="", description="Nombre de la categoría"),
    limit: int = Query(default=50, ge=1, le=200)
):
    """Busca categorías de producto por nombre."""
    try:
        client = get_autopart_client()
        return await client.buscar_categoria(nombre, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categorias/arbol", summary="Árbol de categorías")
async def autopart_arbol_categorias():
    """Muestra la jerarquía de categorías con conteo de aplicaciones."""
    try:
        client = get_autopart_client()
        return await client.arbol_categorias()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════
# Sellers
# ══════════════════════════════════════════════════════════════════════════

@router.get("/vendedores", summary="Buscar vendedores")
async def autopart_buscar_vendedor(
    nombre: str = Query(default="", description="Nombre del vendedor"),
    direccion: str = Query(default="", description="Dirección"),
    limit: int = Query(default=20, ge=1, le=200)
):
    """Busca vendedores por nombre o dirección."""
    try:
        client = get_autopart_client()
        return await client.buscar_vendedor(nombre, direccion, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vendedores/resumen", summary="Resumen de vendedores")
async def autopart_resumen_vendedores(
    limit: int = Query(default=20, ge=1, le=100)
):
    """Resumen de vendedores: publicaciones, precio promedio y rangos."""
    try:
        client = get_autopart_client()
        return await client.resumen_vendedores(limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════
# Applications (Publicaciones)
# ══════════════════════════════════════════════════════════════════════════

@router.get("/aplicaciones", summary="Buscar publicaciones de autopartes")
async def autopart_buscar_aplicacion(
    headline: str = Query(default="", description="Texto en el título"),
    precio_min_usd: float = Query(default=None, description="Precio mínimo USD"),
    precio_max_usd: float = Query(default=None, description="Precio máximo USD"),
    precio_min_gel: float = Query(default=None, description="Precio mínimo GEL"),
    precio_max_gel: float = Query(default=None, description="Precio máximo GEL"),
    condicion: str = Query(default="", description="Condición (New, Used, etc.)"),
    categoria: str = Query(default="", description="Categoría de producto"),
    vendedor: str = Query(default="", description="Nombre del vendedor"),
    estado: str = Query(default="", description="Estado de la publicación"),
    fecha_desde: str = Query(default="", description="YYYY-MM-DD"),
    fecha_hasta: str = Query(default="", description="YYYY-MM-DD"),
    limit: int = Query(default=50, ge=1, le=500)
):
    """Busca publicaciones de autopartes con filtros opcionales."""
    try:
        client = get_autopart_client()
        return await client.buscar_aplicacion(
            headline, precio_min_usd, precio_max_usd,
            precio_min_gel, precio_max_gel, condicion,
            categoria, vendedor, estado, fecha_desde, fecha_hasta, limit
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/aplicaciones/resumen", summary="Resumen de publicaciones")
async def autopart_resumen_aplicaciones(
    agrupar_por: str = Query(default="estado", description="estado | categoria | condicion | vendedor"),
    limit: int = Query(default=20, ge=1, le=100)
):
    """Resumen de publicaciones agrupado por estado, categoría, condición o vendedor."""
    try:
        client = get_autopart_client()
        return await client.resumen_aplicaciones(agrupar_por, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/aplicaciones/top", summary="Top publicaciones por precio")
async def autopart_top_aplicaciones(
    categoria: str = Query(default="", description="Filtrar por categoría"),
    condicion: str = Query(default="", description="Filtrar por condición"),
    ordenar_por: str = Query(default="precio_usd", description="precio_usd | precio_gel"),
    limit: int = Query(default=10, ge=1, le=100)
):
    """Ranking de publicaciones por precio USD o GEL."""
    try:
        client = get_autopart_client()
        return await client.top_aplicaciones(categoria, condicion, ordenar_por, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════
# Compatibility
# ══════════════════════════════════════════════════════════════════════════

@router.get("/compatibilidad", summary="Buscar compatibilidad pieza-vehículo")
async def autopart_buscar_compatibilidad(
    modelo_vehiculo: str = Query(default="", description="Modelo del vehículo"),
    fabricante: str = Query(default="", description="Fabricante del vehículo"),
    anio: int = Query(default=None, description="Año específico"),
    headline: str = Query(default="", description="Texto en el título de la pieza"),
    limit: int = Query(default=50, ge=1, le=500)
):
    """Busca compatibilidades de piezas con vehículos por modelo, fabricante o año."""
    try:
        client = get_autopart_client()
        return await client.buscar_compatibilidad(modelo_vehiculo, fabricante, anio, headline, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/compatibilidad/resumen", summary="Resumen de compatibilidad")
async def autopart_resumen_compatibilidad(
    agrupar_por: str = Query(default="fabricante", description="fabricante | modelo | tipo_vehiculo"),
    limit: int = Query(default=20, ge=1, le=100)
):
    """Resumen de compatibilidades agrupado por fabricante, modelo o tipo de vehículo."""
    try:
        client = get_autopart_client()
        return await client.resumen_compatibilidad(agrupar_por, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
