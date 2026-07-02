"""
ETL - Aeropuerto Internacional Minitos / Hotel International Minitos
======================================================================
Consolida las fuentes de datos del aeropuerto y del hotel en una base
analitica unica (SQLite) lista para alimentar el Dashboard Ejecutivo
en Streamlit (app.py).

Fuentes de entrada (carpeta data/raw/):
    - HotelInternational.accdb   -> tablas Clientes, CheckInHotel, ConsumoHotel
      (si no se puede conectar via ODBC, se usan los CSV exportados de las
      mismas tablas: Clientes.csv, CheckInHotel.csv, ConsumoHotel.csv)
    - reservas.csv                -> Dataset 5: Reservas
    - Geography.txt                -> Dataset 1: Geography (UTF-16, CSV)
    - Currency.txt                  -> Dataset 2: Currency  (UTF-16, CSV)
    - Date.xls                       -> Dataset 3: Date (dimension calendario)
    - moneyExhange.csv                -> Dataset 4: MoneyExchange

Salida:
    data/processed/hotel_analytics.db  (SQLite) con las tablas:
        dim_geography, dim_currency, dim_cliente
        fact_reservas   (una fila por reserva, con USD, check-in, no-show, etc.)
        fact_consumo    (una fila por consumo, con contexto de reserva)
        fact_moneyexchange

Metodologia de conversion a USD (documentada tambien en README.md):
    - reservas.monto_reserva_origen esta en la moneda del CurrencyKey de la
      reserva. Se convierte a USD usando la tasa promedio de esa moneda
      calculada a partir de Dataset 4 (MoneyExchange), ya que ese dataset es
      la unica fuente de tipos de cambio disponible.
    - ConsumoHotel.Monto no trae CurrencyKey y sus magnitudes son
      consistentes con USD directo (montos entre USD 5 y USD 500), por lo
      que se asume que ya esta expresado en USD (tarifario interno del
      hotel). Si en producción se confirma que viene en otra moneda, ajustar
      la funcion `load_consumo()`.
"""

import os
import sqlite3
import pandas as pd

RAW_DIR = os.path.join(os.path.dirname(__file__), "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "data", "processed")
DB_PATH = os.path.join(OUT_DIR, "hotel_analytics.db")

ACCDB_PATH = os.path.join(RAW_DIR, "HotelInternational.accdb")


# ---------------------------------------------------------------------------
# 1. Carga de tablas del Hotel (Access) - Clientes / CheckInHotel / ConsumoHotel
# ---------------------------------------------------------------------------
def _try_load_from_access():
    """
    Intenta leer las 3 tablas directamente desde el .accdb via ODBC.
    Requiere Windows + "Microsoft Access Database Engine" instalado
    (driver: '{Microsoft Access Driver (*.mdb, *.accdb)}').
    Si no esta disponible (Linux/Mac, o el driver no esta instalado),
    devuelve None y el pipeline usa los CSV ya exportados como respaldo.
    """
    try:
        import pyodbc  # pip install pyodbc

        conn_str = (
            r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
            rf"DBQ={ACCDB_PATH};"
        )
        conn = pyodbc.connect(conn_str)
        clientes = pd.read_sql("SELECT * FROM Clientes", conn)
        checkin = pd.read_sql("SELECT * FROM CheckInHotel", conn)
        consumo = pd.read_sql("SELECT * FROM ConsumoHotel", conn)
        conn.close()
        print("[ETL] Tablas leidas directamente desde Access via ODBC.")
        return clientes, checkin, consumo
    except Exception as e:
        print(f"[ETL] No se pudo leer via ODBC ({e}). Se usan los CSV exportados.")
        return None


def load_hotel_tables():
    result = _try_load_from_access()
    if result is not None:
        return result

    clientes = pd.read_csv(os.path.join(RAW_DIR, "Clientes.csv"))
    checkin = pd.read_csv(os.path.join(RAW_DIR, "CheckInHotel.csv"))
    consumo = pd.read_csv(os.path.join(RAW_DIR, "ConsumoHotel.csv"))
    return clientes, checkin, consumo


# ---------------------------------------------------------------------------
# 2. Carga de datasets externos
# ---------------------------------------------------------------------------
def load_geography():
    df = pd.read_csv(os.path.join(RAW_DIR, "Geography.txt"), encoding="utf-16")
    df = df.rename(
        columns={
            "EnglishCountryRegionName": "PaisEN",
            "SpanishCountryRegionName": "Pais",
        }
    )
    return df[["GeographyKey", "City", "CountryRegionCode", "Pais", "PaisEN"]]


def load_currency():
    df = pd.read_csv(os.path.join(RAW_DIR, "Currency.txt"), encoding="utf-16")
    return df.rename(
        columns={"CurrencyAlternateKey": "CodigoMoneda", "CurrencyName": "NombreMoneda"}
    )


def load_date_dimension():
    # Requiere 'xlrd' para .xls legacy: pip install xlrd
    df = pd.read_excel(os.path.join(RAW_DIR, "Date.xls"), engine="xlrd")
    return df


def load_money_exchange():
    df = pd.read_csv(os.path.join(RAW_DIR, "moneyExhange.csv"))
    return df


def load_reservas():
    df = pd.read_csv(os.path.join(RAW_DIR, "reservas.csv"))
    return df


# ---------------------------------------------------------------------------
# 3. Transformaciones / reglas de negocio
# ---------------------------------------------------------------------------
def build_fact_reservas(reservas, checkin, clientes, geography, currency, money_exchange):
    # Tasa de cambio promedio por moneda, calculada desde MoneyExchange
    tasa_promedio = (
        money_exchange.groupby("CurrencyKey")["tasa_cambio_usd"].mean().rename("tasa_promedio_usd")
    )

    df = reservas.merge(tasa_promedio, on="CurrencyKey", how="left")
    # Si una moneda no tiene operaciones registradas en MoneyExchange, se usa
    # la tasa promedio global como respaldo para no perder la reserva.
    df["tasa_promedio_usd"] = df["tasa_promedio_usd"].fillna(
        money_exchange["tasa_cambio_usd"].mean()
    )
    df["monto_reserva_usd"] = df["monto_reserva_origen"] * df["tasa_promedio_usd"]

    # Check-in (1 a 1 por reserva)
    df = df.merge(
        checkin[["ReservaID", "FechaCheckIn", "FechaCheckOut", "Llego", "LateCheckIn", "HoraLlegada"]],
        left_on="id_reserva",
        right_on="ReservaID",
        how="left",
    )

    # Cliente
    df = df.merge(
        clientes[["ClienteID", "NombresCompletos", "CorreoElectronico"]],
        left_on="id_cliente",
        right_on="ClienteID",
        how="left",
    )

    # Geografia de origen del turista
    df = df.merge(geography, on="GeographyKey", how="left")

    # Moneda de la reserva
    df = df.merge(currency, on="CurrencyKey", how="left")

    # Fechas
    df["FechaCheckIn"] = pd.to_datetime(df["FechaCheckIn"], errors="coerce")
    df["FechaCheckOut"] = pd.to_datetime(df["FechaCheckOut"], errors="coerce")

    # Hora de llegada -> a decimal (para promedios) y a datetime (para graficos)
    hora_parsed = pd.to_datetime(df["HoraLlegada"], format="%H:%M", errors="coerce")
    df["HoraLlegada_decimal"] = hora_parsed.dt.hour + hora_parsed.dt.minute / 60

    # Flags de negocio (se derivan de las columnas de texto y luego se
    # descartan las originales para evitar columnas duplicadas en SQLite,
    # que no distingue mayusculas/minusculas en nombres de columna)
    df["es_cancelada"] = df["cancelo_reserva"].eq("Si")
    df["llego"] = df["Llego"].eq("Si")
    df["es_late_checkin"] = df["LateCheckIn"].eq("Si")
    # No-Show real: la reserva NO fue cancelada mas el huesped NO llego
    df["es_no_show"] = (~df["es_cancelada"]) & (~df["llego"])

    df = df.drop(columns=["ReservaID", "ClienteID", "Llego", "LateCheckIn"])
    return df


def build_fact_consumo(consumo, fact_reservas):
    contexto = fact_reservas[
        [
            "id_reserva",
            "Pais",
            "PaisEN",
            "canal_reserva",
            "tipo_habitacion",
            "noches",
            "llego",
            "es_cancelada",
        ]
    ]
    df = consumo.merge(contexto, left_on="ReservaID", right_on="id_reserva", how="left")
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    df = df.drop(columns=["id_reserva"])
    # Monto ya se asume en USD (ver docstring del modulo)
    df = df.rename(columns={"Monto": "Monto_usd"})
    return df


def build_fact_money_exchange(money_exchange, geography, currency, date_dim):
    df = money_exchange.merge(geography, on="GeographyKey", how="left")
    df = df.merge(currency, on="CurrencyKey", how="left")
    df["monto_usd"] = df["monto_origen"] * df["tasa_cambio_usd"]
    date_small = date_dim[["DateKey", "FullDateAlternateKey", "CalendarYear", "MonthNumberOfYear"]]
    df = df.merge(date_small, on="DateKey", how="left")
    return df


# ---------------------------------------------------------------------------
# 4. Orquestacion
# ---------------------------------------------------------------------------
def run():
    os.makedirs(OUT_DIR, exist_ok=True)

    print("[ETL] Cargando tablas del hotel (Access/CSV)...")
    clientes, checkin, consumo = load_hotel_tables()

    print("[ETL] Cargando datasets externos...")
    geography = load_geography()
    currency = load_currency()
    date_dim = load_date_dimension()
    money_exchange = load_money_exchange()
    reservas = load_reservas()

    print("[ETL] Construyendo fact_reservas...")
    fact_reservas = build_fact_reservas(reservas, checkin, clientes, geography, currency, money_exchange)

    print("[ETL] Construyendo fact_consumo...")
    fact_consumo = build_fact_consumo(consumo, fact_reservas)

    print("[ETL] Construyendo fact_moneyexchange...")
    fact_moneyexchange = build_fact_money_exchange(money_exchange, geography, currency, date_dim)

    print(f"[ETL] Escribiendo base analitica en {DB_PATH} ...")
    conn = sqlite3.connect(DB_PATH)
    fact_reservas.to_sql("fact_reservas", conn, if_exists="replace", index=False)
    fact_consumo.to_sql("fact_consumo", conn, if_exists="replace", index=False)
    fact_moneyexchange.to_sql("fact_moneyexchange", conn, if_exists="replace", index=False)
    geography.to_sql("dim_geography", conn, if_exists="replace", index=False)
    currency.to_sql("dim_currency", conn, if_exists="replace", index=False)
    clientes.to_sql("dim_cliente", conn, if_exists="replace", index=False)
    conn.close()

    print("[ETL] Listo.")
    print(f"      fact_reservas:      {len(fact_reservas):,} filas")
    print(f"      fact_consumo:       {len(fact_consumo):,} filas")
    print(f"      fact_moneyexchange: {len(fact_moneyexchange):,} filas")


if __name__ == "__main__":
    run()
