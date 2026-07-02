# Dashboard Ejecutivo — Aeropuerto Internacional Minitos & Hotel International Minitos

Dashboard ejecutivo en **Python + Streamlit** que integra las fuentes de datos del
aeropuerto y del hotel para responder las 13 preguntas estratégicas del negocio,
con todos los montos convertidos a **USD**.

## 1. Estructura del proyecto

```
hotel_dashboard/
├── data/
│   ├── raw/                      # Fuentes originales (Access + datasets)
│   │   ├── HotelInternational.accdb
│   │   ├── Clientes.csv          # export de la tabla Clientes (respaldo si no hay ODBC)
│   │   ├── CheckInHotel.csv      # export de la tabla CheckInHotel
│   │   ├── ConsumoHotel.csv      # export de la tabla ConsumoHotel
│   │   ├── reservas.csv          # Dataset 5: Reservas
│   │   ├── Geography.txt         # Dataset 1: Geography
│   │   ├── Currency.txt          # Dataset 2: Currency
│   │   ├── Date.xls              # Dataset 3: Date
│   │   └── moneyExhange.csv      # Dataset 4: MoneyExchange
│   └── processed/
│       └── hotel_analytics.db    # Base analítica unificada (generada por etl.py)
├── etl.py                        # Consolida todas las fuentes en hotel_analytics.db
├── app.py                        # Dashboard Streamlit
├── requirements.txt
└── README.md
```

## 2. Instalación y ejecución

```bash
pip install -r requirements.txt

# 1) Generar/actualizar la base analítica a partir de data/raw/
python etl.py

# 2) Levantar el dashboard
streamlit run app.py
```

El repositorio ya incluye `data/processed/hotel_analytics.db` pre-generado, por lo
que `streamlit run app.py` funciona de inmediato. Vuelve a correr `etl.py` cada vez
que se actualicen los archivos en `data/raw/`.

### Conexión directa a Access (opcional)

Por defecto el ETL lee las 3 tablas del hotel desde los CSV ya exportados
(`Clientes.csv`, `CheckInHotel.csv`, `ConsumoHotel.csv`), lo cual funciona en
cualquier sistema operativo. Si se ejecuta en **Windows** con el
*Microsoft Access Database Engine* instalado, `etl.py` detecta automáticamente
el driver ODBC y lee **directamente desde `HotelInternational.accdb`** — no se
requiere ningún cambio de código, solo tener `pyodbc` instalado y el driver
disponible en el sistema.

## 3. Modelo de datos

| Tabla (SQLite)        | Grano                        | Fuente                                                              |
|------------------------|-------------------------------|----------------------------------------------------------------------|
| `fact_reservas`        | 1 fila por reserva            | Reservas + CheckInHotel + Clientes + Geography + Currency + MoneyExchange |
| `fact_consumo`         | 1 fila por consumo            | ConsumoHotel + contexto de su reserva (país, canal, habitación)     |
| `fact_moneyexchange`   | 1 fila por operación de cambio| MoneyExchange + Geography + Currency + Date                          |
| `dim_geography` / `dim_currency` / `dim_cliente` | dimensiones | Geography, Currency, Clientes |

## 4. Reglas de negocio y metodología

- **Conversión a USD**: `reservas.monto_reserva_origen` está en la moneda del
  `CurrencyKey` de la reserva. Se convierte a USD usando la **tasa de cambio
  promedio de esa moneda**, calculada desde el dataset `MoneyExchange` (única
  fuente de tipos de cambio disponible). `ConsumoHotel.Monto` no trae moneda de
  origen y sus magnitudes son consistentes con USD directo, por lo que se asume
  ya expresado en USD (tarifario interno del hotel).
- **No-Show real** (pregunta 2): reserva que **no fue cancelada**
  (`cancelo_reserva = No`) pero cuyo huésped **no llegó** (`Llego = No`). Se
  distingue explícitamente de una **cancelación** (el cliente avisó con
  antelación), porque el impacto operativo/comercial es distinto: el no-show
  bloquea inventario que pudo venderse.
- **Late Check-In** (pregunta 6): se toma el flag `LateCheckIn` de la tabla
  `CheckInHotel`, calculado solo sobre huéspedes que efectivamente llegaron.
- **Nacionalidad / país de origen**: se obtiene de `GeographyKey` en la tabla
  `Reservas`, enlazado al dataset `Geography`.
- Los países con **menos de 15 reservas** en el filtro activo se excluyen de los
  rankings de no-show por país, para evitar que un solo caso aislado infle un
  porcentaje.

## 5. Preguntas de negocio cubiertas

| # | Pregunta | Sección del dashboard |
|---|----------|------------------------|
| 1 | % de reservas que llegó al hotel | Ocupación y Asistencia |
| 2 | % de No-Show | Ocupación y Asistencia |
| 3 | Canales con mayor % de no asistencia | Ocupación y Asistencia |
| 4 | Países con más no-show | Ocupación y Asistencia |
| 5 | Hora promedio de llegada | Ocupación y Asistencia |
| 6 | % de Late Check-In | Ocupación y Asistencia |
| 7 | Categoría con mayores ingresos | Consumo y Rentabilidad |
| 8 | Categoría más utilizada | Consumo y Rentabilidad |
| 9 | Nacionalidad que más consume | Nacionalidad y Geografía |
| 10 | Método de pago más utilizado | Consumo y Rentabilidad |
| 11 | Categoría con ticket promedio más alto | Consumo y Rentabilidad |
| 12 | Relación noches vs. gasto total | Habitaciones y Estadía |
| 13 | Tipo de habitación que más consume servicios | Habitaciones y Estadía |

## 6. Secciones del dashboard (4, mínimo solicitado: 3)

1. **✈️ Ocupación y Asistencia** — preguntas 1, 2, 3, 4, 5, 6
2. **💰 Consumo y Rentabilidad** — preguntas 7, 8, 10, 11
3. **🏨 Habitaciones y Estadía** — preguntas 12, 13
4. **🌍 Nacionalidad y Geografía** — pregunta 9 + contexto geográfico

Todas las secciones responden a los filtros globales del sidebar (rango de
fechas de check-in, país de origen, canal de reserva, tipo de habitación).
