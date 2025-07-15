import streamlit as st
import folium
from streamlit_folium import st_folium
import random
from datetime import time

st.set_page_config(layout="wide", page_title="Sistema de Patrullas", page_icon="🚓")

calles_tacna = [
    "Universidad Nacional", "Tacna centro", "Hospital Hipolito Unane", "Mercado 2 de Mayo", "Polvos rosados",
    "Plaza quiñones", "Solari", "Paseo civico", "Catedral", "Mercado santa rosa", "Cenepa"
]

def generar_patrullas(n):
    return [(-18.006 + random.uniform(-0.01, 0.01), -70.246 + random.uniform(-0.01, 0.01)) for _ in range(n)]

def mover_patrullas(patrullas):
    return [(lat + random.uniform(-0.001, 0.001), lon + random.uniform(-0.001, 0.001)) for lat, lon in patrullas]

def generar_posicion_para_calle(calle):
    base = {
        "Universidad Nacional": (-18.0045, -70.2450),
        "Tacna centro": (-18.0020, -70.2400),
        "Hospital Hipolito Unane": (-18.0060, -70.2475),
        "Mercado 2 de Mayo": (-18.0070, -70.2490),
        "Cenepa": (-18.0080, -70.2440),
        "Mercado santa rosa": (-18.0095, -70.2420),
        "Polvos rosados": (-18.0110, -70.2500),
        "Plaza quiñones": (-18.0100, -70.2470),
        "Solari": (-18.0030, -70.2415),
        "Paseo civico": (-18.0055, -70.2435),
        "Catedral": (-18.0075, -70.2435),
        # Coordenadas para las avenidas (pueden ser puntos representativos)
        "Av. Bolognesi": (-18.0135, -70.2515),
        "Av. Basadre y Forero": (-18.0200, -70.2530),
        "Av. Leguía": (-18.0150, -70.2480),
        "Jr. 2 de Mayo": (-18.0142, -70.2525),
        "Jr. Inclán": (-18.0125, -70.2505),
        "Av. Patricio Meléndez": (-18.0118, -70.2495),
        "Av. Industrial": (-17.9950, -70.2350),
        "Av. Dos de Mayo": (-18.0142, -70.2525),
        "Av. Jorge Basadre": (-18.0200, -70.2530),
        "Av. Pinto": (-18.0085, -70.2400)
    }
    return base.get(calle, (-18.0066, -70.2463)) # Devuelve una posición por defecto si no la encuentra

if "n_patrullas" not in st.session_state:
    st.session_state.n_patrullas = 5
if "patrullas" not in st.session_state:
    st.session_state.patrullas = generar_patrullas(5)
if "movimiento_inicial" not in st.session_state:
    st.session_state.patrullas = mover_patrullas(st.session_state.patrullas)
    st.session_state.movimiento_inicial = True
if "incidentes" not in st.session_state:
    st.session_state.incidentes = []
if "evento" not in st.session_state:
    st.session_state.evento = None
if "mostrar_panel" not in st.session_state:
    st.session_state.mostrar_panel = True
# ===== NUEVO ESTADO DE SESIÓN PARA EL MODO DE ADICIÓN =====
if "add_patrol_mode" not in st.session_state:
    st.session_state.add_patrol_mode = False


# panel laterak
with st.sidebar:
    if st.session_state.mostrar_panel:
        st.markdown("<h3 style='text-align: center; margin-bottom: 0.05px;'>🗺️ Sistema de Patrullaje Inteligente</h4>", unsafe_allow_html=True)
        st.caption("**Proyecto de Sistemas Expertos – UNJBG**")
        st.markdown("---")

        st.markdown("#### ⚙️ Configuración")
        n = st.slider("🚓 Número de Patrullas", 1, 20, st.session_state.n_patrullas, key="slider_n_patrullas")
        if n != st.session_state.n_patrullas:
             st.session_state.n_patrullas = n
             st.session_state.patrullas = generar_patrullas(n)
             st.rerun()

        # añado partullas
        st.markdown("#### 🖱️ Añadir Patrulla con Clic")
        st.session_state.add_patrol_mode = st.toggle("Activar modo de adición", value=st.session_state.add_patrol_mode)
        if st.session_state.add_patrol_mode:
            st.info("Modo activado: Haz clic en el mapa para añadir una nueva patrulla en esa ubicación.")

        st.markdown("---") # Separador visual

        hora = st.time_input("🕐 Hora actual", time(7, 30))
        clima = st.selectbox("🌤️ Clima actual", ["Soleado", "Lluvia", "Niebla"])

        st.markdown("#### 🚧 Incidente Imprevisto")
        calle_incidente = st.selectbox("Seleccionar Calle", calles_tacna, key="incidente_calle")
        tipo_incidente = st.radio("Tipo", ["Accidente", "Bloqueo", "Obra"], key="tipo_inc")
        if st.button("📍 Agregar Incidente"):
            pos = generar_posicion_para_calle(calle_incidente)
            st.session_state.incidentes.append({
                "calle": calle_incidente,
                "tipo": tipo_incidente,
                "pos": pos
            })
            st.rerun()

        st.markdown("#### 📍 Evento de Emergencia")
        evento_tipo = st.selectbox("Tipo de Evento", ["Robo", "Asalto", "Denuncia", "Accidente", "Otro"])
        evento_calle = st.selectbox("Ubicación del Evento", calles_tacna)
        if st.button("📡 Despachar Patrulla"):
            pos = generar_posicion_para_calle(evento_calle)
            st.session_state.evento = {"tipo": evento_tipo, "calle": evento_calle, "pos": pos}
            st.success(f"🆘 Evento '{evento_tipo}' en {evento_calle}")
            st.info("Buscando patrulla más cercana...")

            st.markdown("##### 📊 Rutas Candidatas")
            st.table({
                "Ruta": ["Ruta 1", "Ruta 2", "Ruta 3"],
                "Distancia (km)": [1.2, 1.5, 1.7],
                "Tiempo estimado (min)": [3.2, 4.0, 4.5],
                "Riesgo estimado": ["Bajo", "Alto", "Medio"]
            })
        if st.button("Ruta segura"):
            st.success("Ruta segura seleccionada.")
        if st.button("Ruta Rapida"):
            st.success("Ruta rápida seleccionada.")

# ================= MAPA =================
mapa = folium.Map(location=[-18.0066, -70.2463], zoom_start=15) # Ajuste de zoom

# Patrullas
for i, (lat, lon) in enumerate(st.session_state.patrullas):
    folium.Marker([lat, lon],
                  popup=f"🚓 Patrulla {i+1}",
                  icon=folium.Icon(color="blue", icon="car", prefix="fa")).add_to(mapa)

# Incidentes
for incidente in st.session_state.incidentes:
    color = "orange" if incidente["tipo"] == "Obra" else "red"
    icono = "ban" if incidente["tipo"] == "Bloqueo" else "exclamation-triangle"
    folium.Marker(
        location=incidente["pos"],
        popup=f"{incidente['tipo']} en {incidente['calle']}",
        icon=folium.Icon(color=color, icon=icono, prefix="fa")
    ).add_to(mapa)

# Evento
if st.session_state.evento:
    evento = st.session_state.evento
    folium.Marker(
        location=evento["pos"],
        popup=f"🆘 {evento['tipo']} en {evento['calle']}",
        icon=folium.Icon(color="green", icon="info-sign")
    ).add_to(mapa)

# ========== CSS para estilo ==========
st.markdown("""
    <style>
        /* Reduce el padding superior del contenedor principal */
        .main .block-container {
            padding-top: 1rem; 
            padding-bottom: 1rem;
        }
    </style>
""", unsafe_allow_html=True)

# ===== RENDERIZAR EL MAPA Y CAPTURAR INTERACCIONES =====
# Se guarda el estado del mapa en la variable 'map_data'
map_data = st_folium(mapa, use_container_width=True, height=700)

# ===== LÓGICA PARA AÑADIR PATRULLA AL HACER CLIC =====
# Se comprueba si el modo de adición está activo y si el usuario hizo clic en el mapa
if st.session_state.add_patrol_mode and map_data and map_data["last_clicked"]:
    # Se obtienen las coordenadas del clic. Nota: folium devuelve 'lng' en lugar de 'lon'
    lat = map_data["last_clicked"]["lat"]
    lon = map_data["last_clicked"]["lng"]
    
    # Se añaden las nuevas coordenadas a la lista de patrullas
    st.session_state.patrullas.append((lat, lon))
    
    # Se actualiza el contador de patrullas en el slider
    st.session_state.n_patrullas = len(st.session_state.patrullas)
    
    # Se desactiva el modo para evitar añadir más patrullas por accidente
    st.session_state.add_patrol_mode = False
    
    # st.rerun() fuerza la recarga de la app para mostrar la nueva patrulla inmediatamente
    st.rerun()