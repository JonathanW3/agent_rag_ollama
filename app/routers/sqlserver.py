from fastapi import APIRouter, HTTPException, Query
from ..schemas import SqlServerQueryRequest
from mcp_sqlserver.client import get_webpos_client
from app.db_platform import set_licenciamiento

router = APIRouter(prefix="/webpospa", tags=["🗃️ SQL Server Webpospa"])


@router.get("/licencias/ecuador/buscar", summary="Buscar empresa en Ecuador")
async def buscar_empresa_ecuador(
    nombre: str = Query(default="", description="Nombre de la empresa — búsqueda parcial (LIKE)"),
    ruc: str = Query(default="", description="CompanyRUC — búsqueda parcial (LIKE)"),
    licenciamiento: bool | None = Query(default=None, description="true=Licenciamiento local, false=Nube, omitir=todos"),
):
    """
    Busca empresas en la base local (MySQL) por nombre, RUC y/o tipo de contrato.
    - **nombre**: búsqueda parcial, no distingue mayúsculas
    - **ruc**: búsqueda parcial
    - **licenciamiento**: `true` = instalación local, `false` = Nube
    """
    try:
        client = get_webpos_client()
        return await client.buscar_empresa_ecuador(
            nombre=nombre,
            ruc=ruc,
            licenciamiento=licenciamiento,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/licencias/ecuador/resumen", summary="Resumen liviano de empresas por tipo de contrato")
async def resumen_tipo_licenciamiento(
    licenciamiento: bool | None = Query(
        default=None,
        description="true = Licenciamiento (on-premise), false = Nube, omitir = todos",
    ),
):
    """
    Retorna un resumen de empresas Ecuador **sin** el detalle de licencias individuales.
    Útil para listar rápidamente todas las empresas de un tipo sin saturar el contexto.
    Campos: CompanyRUC, CompanyName, ContactEmail, TotalLicencias, EFiscalDocsCount,
    EFiscalDocsExpirationDate, MinExpirationDate, MinSwSExpirationDate, Licenciamiento.
    """
    try:
        client = get_webpos_client()
        return await client.resumen_tipo_licenciamiento(licenciamiento=licenciamiento)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/licencias/ecuador/por-vencer", summary="Licencias próximas a vencer")
async def licencias_por_vencer(
    dias: int = Query(default=45, ge=1, le=365, description="Días hacia adelante para buscar vencimientos"),
    campo_fecha: str = Query(
        default="ambas",
        description="ExpirationDate | SwSExpirationDate | ambas",
    ),
):
    """
    Lista las licencias de Ecuador que vencen en los próximos N días.
    Consulta la base local (MySQL) — datos actualizados en el último sync.
    Incluye **DiasParaExpiracion**, **DiasParaSwSExpiracion** y el flag **Licenciamiento**.
    """
    try:
        client = get_webpos_client()
        return await client.licencias_por_vencer(dias=dias, campo_fecha=campo_fecha)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/licencias/ecuador/sync", summary="Sincronizar SQL Server → MySQL ahora")
async def sync_licencias_ecuador():
    """
    Fuerza una sincronización inmediata de los datos de licencias.
    Normalmente el cron lo hace a las **8:00** y **14:00**.
    Retorna la cantidad de empresas sincronizadas.
    """
    try:
        client = get_webpos_client()
        return await client.sync_licencias_ecuador()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch(
    "/licencias/ecuador/{ruc}/licenciamiento",
    summary="Marcar empresa como Licenciamiento (on-premise) o Nube",
)
async def set_tipo_licenciamiento(
    ruc: str,
    valor: bool = Query(description="true = Licenciamiento on-premise, false = Nube"),
):
    """
    Establece el tipo de contrato de una empresa en la base local.
    Este campo **no se sobreescribe** en los syncs automáticos, por lo que
    solo necesita configurarse una vez por empresa.
    - `true` → Licenciamiento (instalación on-premise, prioridad alta)
    - `false` → Nube
    """
    encontrado = set_licenciamiento(ruc, valor)
    if not encontrado:
        raise HTTPException(status_code=404, detail=f"Empresa con RUC '{ruc}' no encontrada.")
    return {
        "success": True,
        "CompanyRUC": ruc,
        "Licenciamiento": valor,
        "message": f"Empresa marcada como {'Licenciamiento (on-premise)' if valor else 'Nube'}.",
    }


@router.post("/query", summary="Consulta SELECT libre en webpospa (SQL Server directo)")
async def webpospa_query(request: SqlServerQueryRequest):
    """
    Ejecuta cualquier SELECT directamente en la base de datos webpospa (SQL Server).
    Solo lectura. Usa **?** como placeholder.
    Tabla: [webpospa].[dbo].[RegisteredLicenses]
    """
    try:
        client = get_webpos_client()
        return await client.query(request.query, request.params or None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
