"""
Dashboard Ejecutivo - Aeropuerto Internacional Minitos / Hotel International Minitos
======================================================================================
Streamlit + Plotly. Lee la base analitica generada por etl.py
(data/processed/hotel_analytics.db) y responde a las 13 preguntas de negocio
solicitadas por la direccion ejecutiva. Todos los montos se muestran en USD.

Ejecutar:
    streamlit run app.py
"""

import os
import sqlite3

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "processed", "hotel_analytics.db")

st.set_page_config(
    page_title="Hotel International Minitos | Dashboard Ejecutivo",
    page_icon="🏨",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------
@st.cache_data
def load_data():
    conn = sqlite3.connect(DB_PATH)
    reservas = pd.read_sql("SELECT * FROM fact_reservas", conn)
    consumo = pd.read_sql("SELECT * FROM fact_consumo", conn)
    conn.close()

    reservas["FechaCheckIn"] = pd.to_datetime(reservas["FechaCheckIn"], errors="coerce")
    reservas["FechaCheckOut"] = pd.to_datetime(reservas["FechaCheckOut"], errors="coerce")
    consumo["Fecha"] = pd.to_datetime(consumo["Fecha"], errors="coerce")

    for col in ["llego", "es_cancelada", "es_late_checkin", "es_no_show"]:
        reservas[col] = reservas[col].astype(bool)
    for col in ["llego", "es_cancelada"]:
        consumo[col] = consumo[col].astype(bool)

    return reservas, consumo


if not os.path.exists(DB_PATH):
    st.error(
        "No se encontro la base analitica en "
        f"`{DB_PATH}`. Ejecuta primero `python etl.py` para generarla."
    )
    st.stop()

reservas, consumo = load_data()

# ---------------------------------------------------------------------------
# Sidebar - Filtros
# ---------------------------------------------------------------------------
st.sidebar.title("🏨 Filtros")

fecha_min = reservas["FechaCheckIn"].min()
fecha_max = reservas["FechaCheckIn"].max()
rango_fechas = st.sidebar.date_input(
    "Rango de Check-In",
    value=(fecha_min.date(), fecha_max.date()),
    min_value=fecha_min.date(),
    max_value=fecha_max.date(),
)

paises_disp = sorted(reservas["Pais"].dropna().unique().tolist())
paises_sel = st.sidebar.multiselect("País de origen", paises_disp, default=[])

canales_disp = sorted(reservas["canal_reserva"].dropna().unique().tolist())
canales_sel = st.sidebar.multiselect("Canal de reserva", canales_disp, default=[])

habitaciones_disp = sorted(reservas["tipo_habitacion"].dropna().unique().tolist())
habitaciones_sel = st.sidebar.multiselect("Tipo de habitación", habitaciones_disp, default=[])

# Aplicar filtros
r = reservas.copy()
if isinstance(rango_fechas, tuple) and len(rango_fechas) == 2:
    ini, fin = pd.Timestamp(rango_fechas[0]), pd.Timestamp(rango_fechas[1])
    r = r[(r["FechaCheckIn"] >= ini) & (r["FechaCheckIn"] <= fin)]
if paises_sel:
    r = r[r["Pais"].isin(paises_sel)]
if canales_sel:
    r = r[r["canal_reserva"].isin(canales_sel)]
if habitaciones_sel:
    r = r[r["tipo_habitacion"].isin(habitaciones_sel)]

c = consumo[consumo["ReservaID"].isin(r["id_reserva"])].copy()

st.sidebar.markdown("---")
st.sidebar.caption(
    f"Reservas en el filtro actual: **{len(r):,}** de {len(reservas):,}\n\n"
    f"Consumos en el filtro actual: **{len(c):,}** de {len(consumo):,}"
)

# ---------------------------------------------------------------------------
# Encabezado + KPIs
# ---------------------------------------------------------------------------
st.title("🏨 Dashboard Ejecutivo — Hotel International Minitos")
st.caption(
    "Recorrido del turista internacional: llegada al país → cambio de divisas → "
    "reserva → check-in → consumo dentro del hotel. Todos los montos en USD."
)

if len(r) == 0:
    st.warning("No hay datos para los filtros seleccionados.")
    st.stop()

k1, k2, k3, k4, k5, k6 = st.columns(6)
pct_llegaron = r["llego"].mean() * 100
pct_no_show = r["es_no_show"].mean() * 100
pct_cancel = r["es_cancelada"].mean() * 100
hora_prom = r.loc[r["llego"], "HoraLlegada_decimal"].mean()
pct_late = r.loc[r["llego"], "es_late_checkin"].mean() * 100 if r["llego"].any() else 0
ingreso_consumo = c["Monto_usd"].sum()

k1.metric("Reservas totales", f"{len(r):,}")
k2.metric("% Llegó al hotel", f"{pct_llegaron:.1f}%")
k3.metric("% No-Show", f"{pct_no_show:.1f}%")
k4.metric("% Cancelación", f"{pct_cancel:.1f}%")
k5.metric("Hora prom. llegada", f"{int(hora_prom):02d}:{int((hora_prom % 1) * 60):02d}" if pd.notna(hora_prom) else "N/D")
k6.metric("Ingreso por consumo", f"US$ {ingreso_consumo:,.0f}")

st.markdown("---")

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "✈️ Ocupación y Asistencia",
        "💰 Consumo y Rentabilidad",
        "🏨 Habitaciones y Estadía",
        "🌍 Nacionalidad y Geografía",
    ]
)

# ---------------------------------------------------------------------------
# TAB 1 - Ocupación y Asistencia (Preguntas 1, 2, 3, 4, 5, 6)
# ---------------------------------------------------------------------------
with tab1:
    st.subheader("¿Qué porcentaje de reservas realmente llegó al hotel?")
    col1, col2 = st.columns([1, 2])
    with col1:
        fig = go.Figure(
            go.Pie(
                labels=["Llegó", "No llegó"],
                values=[r["llego"].sum(), (~r["llego"]).sum()],
                hole=0.55,
                marker_colors=["#2E86AB", "#E63946"],
            )
        )
        fig.update_layout(title="Asistencia real vs. reservas totales", height=350)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.markdown(
            f"- **{pct_llegaron:.1f}%** de las reservas ({r['llego'].sum():,} de {len(r):,}) "
            "se concretaron con la llegada del huésped al hotel.\n"
            f"- **{pct_cancel:.1f}%** fueron canceladas explícitamente antes de la fecha.\n"
            f"- **{pct_no_show:.1f}%** corresponden a **No-Show real**: la reserva "
            "no fue cancelada, pero el huésped nunca llegó (una pérdida silenciosa "
            "de inventario que la cancelación no captura)."
        )

    st.markdown("---")
    colA, colB = st.columns(2)

    with colA:
        st.subheader("¿Qué canales presentan mayor % de no asistencia?")
        by_canal = (
            r.groupby("canal_reserva")
            .agg(no_show_pct=("es_no_show", "mean"), reservas=("id_reserva", "count"))
            .reset_index()
        )
        by_canal["no_show_pct"] *= 100
        by_canal = by_canal.sort_values("no_show_pct", ascending=False)
        fig = px.bar(
            by_canal,
            x="canal_reserva",
            y="no_show_pct",
            text=by_canal["no_show_pct"].round(1),
            labels={"canal_reserva": "Canal de reserva", "no_show_pct": "% No-Show"},
            color="no_show_pct",
            color_continuous_scale="Reds",
        )
        fig.update_traces(texttemplate="%{text}%", textposition="outside")
        fig.update_layout(height=380, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    with colB:
        st.subheader("¿Qué países presentan más clientes que no llegan?")
        by_pais = (
            r.groupby("Pais")
            .agg(no_show_pct=("es_no_show", "mean"), reservas=("id_reserva", "count"))
            .reset_index()
        )
        by_pais = by_pais[by_pais["reservas"] >= 15]  # evita ruido de países con pocas reservas
        by_pais["no_show_pct"] *= 100
        by_pais = by_pais.sort_values("no_show_pct", ascending=False).head(10)
        fig = px.bar(
            by_pais.sort_values("no_show_pct"),
            x="no_show_pct",
            y="Pais",
            orientation="h",
            text=by_pais.sort_values("no_show_pct")["no_show_pct"].round(1),
            labels={"Pais": "País", "no_show_pct": "% No-Show"},
            color="no_show_pct",
            color_continuous_scale="Reds",
        )
        fig.update_traces(texttemplate="%{text}%", textposition="outside")
        fig.update_layout(height=380, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)
    st.caption("Se excluyen países con menos de 15 reservas en el filtro actual para evitar distorsión estadística.")

    st.markdown("---")
    colC, colD = st.columns(2)

    with colC:
        st.subheader("¿Cuál es la hora promedio de llegada de los huéspedes?")
        llegaron = r[r["llego"]]
        fig = px.histogram(
            llegaron,
            x="HoraLlegada_decimal",
            nbins=24,
            labels={"HoraLlegada_decimal": "Hora del día"},
        )
        fig.add_vline(x=hora_prom, line_dash="dash", line_color="red")
        fig.update_layout(
            height=380,
            title=f"Hora promedio: {int(hora_prom):02d}:{int((hora_prom % 1) * 60):02d}",
        )
        st.plotly_chart(fig, use_container_width=True)

    with colD:
        st.subheader("¿Qué porcentaje realiza Late Check-In?")
        fig = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=pct_late,
                number={"suffix": "%"},
                gauge={"axis": {"range": [0, 100]}, "bar": {"color": "#E63946"}},
                title={"text": "% Late Check-In (sobre huéspedes que llegaron)"},
            )
        )
        fig.update_layout(height=380)
        st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# TAB 2 - Consumo y Rentabilidad (Preguntas 7, 8, 9, 10, 11)
# ---------------------------------------------------------------------------
with tab2:
    st.subheader("¿Qué categoría genera mayores ingresos y cuál es la más utilizada?")
    colA, colB = st.columns(2)
    with colA:
        rev_cat = c.groupby("Categoria")["Monto_usd"].sum().sort_values(ascending=False).reset_index()
        fig = px.bar(
            rev_cat,
            x="Monto_usd",
            y="Categoria",
            orientation="h",
            text=rev_cat["Monto_usd"].map(lambda v: f"US$ {v:,.0f}"),
            labels={"Monto_usd": "Ingreso (USD)", "Categoria": "Categoría"},
            color="Monto_usd",
            color_continuous_scale="Teal",
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(height=400, coloraxis_showscale=False, title="Ingresos por categoría (USD)")
        st.plotly_chart(fig, use_container_width=True)

    with colB:
        uso_cat = c["Categoria"].value_counts().reset_index()
        uso_cat.columns = ["Categoria", "Consumos"]
        fig = px.bar(
            uso_cat.sort_values("Consumos"),
            x="Consumos",
            y="Categoria",
            orientation="h",
            text="Consumos",
            color="Consumos",
            color_continuous_scale="Purp",
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(height=400, coloraxis_showscale=False, title="Categoría más utilizada (# de consumos)")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    colC, colD = st.columns(2)
    with colC:
        st.subheader("¿Qué método de pago es el más utilizado?")
        pago = c["MetodoPago"].value_counts().reset_index()
        pago.columns = ["MetodoPago", "Transacciones"]
        fig = px.pie(pago, names="MetodoPago", values="Transacciones", hole=0.45)
        fig.update_layout(height=380)
        st.plotly_chart(fig, use_container_width=True)

    with colD:
        st.subheader("¿Qué categoría presenta el ticket promedio más alto?")
        ticket = c.groupby("Categoria")["Monto_usd"].mean().sort_values(ascending=False).reset_index()
        fig = px.bar(
            ticket,
            x="Categoria",
            y="Monto_usd",
            text=ticket["Monto_usd"].map(lambda v: f"US$ {v:,.1f}"),
            labels={"Monto_usd": "Ticket promedio (USD)"},
            color="Monto_usd",
            color_continuous_scale="Oranges",
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(height=380, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# TAB 3 - Habitaciones y Estadía (Preguntas 12, 13)
# ---------------------------------------------------------------------------
with tab3:
    st.subheader("¿Existe relación entre la cantidad de noches y el gasto total del huésped?")

    gasto_por_reserva = c.groupby("ReservaID")["Monto_usd"].sum().rename("gasto_total")
    r_gasto = r.merge(gasto_por_reserva, left_on="id_reserva", right_index=True, how="left")
    r_gasto["gasto_total"] = r_gasto["gasto_total"].fillna(0)
    r_gasto_llegaron = r_gasto[r_gasto["llego"]]

    correlacion = r_gasto_llegaron["noches"].corr(r_gasto_llegaron["gasto_total"])

    colA, colB = st.columns([2, 1])
    with colA:
        fig = px.scatter(
            r_gasto_llegaron,
            x="noches",
            y="gasto_total",
            trendline="ols",
            opacity=0.35,
            labels={"noches": "Noches de estadía", "gasto_total": "Gasto total en consumo (USD)"},
        )
        fig.update_layout(height=420)
        st.plotly_chart(fig, use_container_width=True)
    with colB:
        st.metric("Coeficiente de correlación (Pearson)", f"{correlacion:.3f}")
        if abs(correlacion) < 0.2:
            interpretacion = (
                "La correlación es prácticamente nula: **la cantidad de noches no explica "
                "el gasto en consumos**. El gasto depende más del comportamiento individual "
                "del huésped que de la duración de la estadía."
            )
        elif correlacion > 0:
            interpretacion = "Existe una relación positiva: a más noches, tiende a haber mayor gasto."
        else:
            interpretacion = "Existe una relación negativa entre noches y gasto."
        st.info(interpretacion)

    st.markdown("---")
    st.subheader("¿Qué tipo de habitación consume más servicios adicionales?")
    colC, colD = st.columns(2)
    with colC:
        by_room = r_gasto.groupby("tipo_habitacion")["gasto_total"].mean().sort_values(ascending=False).reset_index()
        fig = px.bar(
            by_room,
            x="tipo_habitacion",
            y="gasto_total",
            text=by_room["gasto_total"].map(lambda v: f"US$ {v:,.0f}"),
            labels={"tipo_habitacion": "Tipo de habitación", "gasto_total": "Gasto promedio en consumo (USD)"},
            color="gasto_total",
            color_continuous_scale="Blues",
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(height=400, coloraxis_showscale=False, title="Gasto promedio en servicios por tipo de habitación")
        st.plotly_chart(fig, use_container_width=True)
    with colD:
        mix = c.groupby(["tipo_habitacion", "Categoria"])["Monto_usd"].sum().reset_index()
        fig = px.bar(
            mix,
            x="tipo_habitacion",
            y="Monto_usd",
            color="Categoria",
            labels={"tipo_habitacion": "Tipo de habitación", "Monto_usd": "Ingreso por consumo (USD)"},
        )
        fig.update_layout(height=400, title="Mix de consumo por tipo de habitación")
        st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# TAB 4 - Nacionalidad y Geografía (Pregunta 9 + contexto geográfico)
# ---------------------------------------------------------------------------
with tab4:
    st.subheader("¿Qué nacionalidad consume más dinero dentro del hotel?")
    by_nac = c.groupby("Pais")["Monto_usd"].sum().sort_values(ascending=False).head(15).reset_index()
    fig = px.bar(
        by_nac.sort_values("Monto_usd"),
        x="Monto_usd",
        y="Pais",
        orientation="h",
        text=by_nac.sort_values("Monto_usd")["Monto_usd"].map(lambda v: f"US$ {v:,.0f}"),
        labels={"Monto_usd": "Consumo total (USD)", "Pais": "País de origen"},
        color="Monto_usd",
        color_continuous_scale="Greens",
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(height=500, coloraxis_showscale=False, title="Top 15 países por consumo dentro del hotel")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.subheader("Reservas por país de origen")
    by_pais_reservas = r["Pais"].value_counts().head(15).reset_index()
    by_pais_reservas.columns = ["Pais", "Reservas"]
    fig = px.bar(
        by_pais_reservas.sort_values("Reservas"),
        x="Reservas",
        y="Pais",
        orientation="h",
        color="Reservas",
        color_continuous_scale="Blues",
    )
    fig.update_layout(height=500, coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.caption(
    "Metodología: los montos de Reservas se convierten a USD usando la tasa de cambio "
    "promedio por moneda calculada a partir del dataset MoneyExchange. Los montos de "
    "ConsumoHotel se asumen ya expresados en USD (tarifario interno del hotel). "
    "No-Show = reserva no cancelada cuyo huésped no llegó."
)
