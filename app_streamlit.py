import streamlit as st
import folium
from streamlit_folium import st_folium
import numpy as np
import time
import random
import math
from folium.plugins import MarkerCluster
import base64
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

# Configuración de la página
st.set_page_config(
    page_title="Sistema de Patrullas Tacna",
    page_icon="🚔",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título principal
st.title("🚔 Sistema de Patrullas - Tacna, Perú")

# Coordenadas del centro de Tacna
TACNA_CENTER = [-18.0146, -70.2535]

# Sidebar para configuración
st.sidebar.header("Configuración de Patrullas")

# Selector de número de patrullas
num_patrullas = st.sidebar.selectbox(
    "Patrullas:",
    options=list(range(1, 11)),
    index=4,  # Por defecto 5 patrullas
    format_func=lambda x: f"Patrullas [{x}]"
)

# Selector de hora
st.sidebar.markdown("---")
st.sidebar.subheader("⏰ Hora del Día")

import datetime
hora_seleccionada = st.sidebar.time_input(
    "Selecciona la hora:",
    value=datetime.time(14, 30),  # 2:30 PM por defecto
    help="Cambia la hora para simular diferentes condiciones de tráfico"
)

# Función para determinar el nivel de tráfico
def determinar_trafico(hora_obj):
    """Determina el nivel de tráfico basado en la hora"""
    hora = hora_obj.hour
    minuto = hora_obj.minute
    hora_decimal = hora + minuto / 60
    
    if 6.5 <= hora_decimal < 8:  # 6:30 AM - 8:00 AM
        return "🔴 FULL TRÁFICO", "Hora pico matutina - Congestión severa", "#FF0000"
    elif 8 <= hora_decimal < 11:  # 8:00 AM - 11:00 AM
        return "🟡 MEDIO TRÁFICO", "Tráfico moderado - Flujo constante", "#FFA500"
    elif 11 <= hora_decimal < 13:  # 11:00 AM - 1:00 PM
        return "🔴 FULL TRÁFICO", "Hora de almuerzo - Mucho movimiento", "#FF0000"
    elif 13 <= hora_decimal < 17:  # 1:00 PM - 5:00 PM
        return "🟡 MEDIO TRÁFICO", "Tarde tranquila - Flujo moderado", "#FFA500"
    elif 17 <= hora_decimal < 20:  # 5:00 PM - 8:00 PM
        return "🟥 MUCHO TRÁFICO", "Hora pico vespertina - Congestión intensa", "#8B0000"
    elif 20 <= hora_decimal < 23:  # 8:00 PM - 11:00 PM
        return "🟢 POCO TRÁFICO", "Noche temprana - Tráfico ligero", "#32CD32"
    else:  # 11:00 PM - 6:30 AM
        return "🔵 SIN TRÁFICO", "Madrugada - Calles libres", "#0000FF"

# Mostrar estado del tráfico
nivel_trafico, descripcion_trafico, color_trafico = determinar_trafico(hora_seleccionada)

# Mostrar el estado del tráfico de manera más simple
st.sidebar.markdown(f"**Estado del Tráfico ({hora_seleccionada.strftime('%H:%M')})**")
st.sidebar.markdown(f"{nivel_trafico}")
st.sidebar.markdown(f"*{descripcion_trafico}*")

# Selector de clima
st.sidebar.markdown("---")
st.sidebar.subheader("🌤️ Condiciones Climáticas")

# Opciones de clima simplificadas
opciones_clima_simple = [
    "☀️ Soleado",
    "⛅ Parcialmente Nublado", 
    "☁️ Nublado",
    "🌦️ Lluvia Ligera",
    "🌧️ Lluvia Intensa",
    "⛈️ Tormenta",
    "🌫️ Niebla",
    "💨 Ventoso"
]

clima_seleccionado_idx = st.sidebar.selectbox(
    "Selecciona el clima:",
    options=range(len(opciones_clima_simple)),
    index=0,  # Soleado por defecto
    format_func=lambda x: opciones_clima_simple[x],
    help="Elige las condiciones climáticas para la simulación"
)

# Mapear el índice seleccionado al clima correspondiente
mapeo_clima = {
    0: "soleado",
    1: "parcialmente_nublado",
    2: "nublado", 
    3: "lluvia_ligera",
    4: "lluvia_intensa",
    5: "tormenta",
    6: "niebla",
    7: "viento"
}

clima_seleccionado = mapeo_clima[clima_seleccionado_idx]

# Función para obtener detalles del clima
def obtener_detalles_clima(clima):
    """Obtiene detalles y efectos del clima seleccionado"""
    detalles_clima = {
        "soleado": {
            "descripcion": "Cielo despejado, excelente visibilidad",
            "efectos": "Condiciones ideales para patrullaje",
            "velocidad_factor": 1.0,
            "color": "#FFD700",
            "icono": "☀️"
        },
        "parcialmente_nublado": {
            "descripcion": "Algunas nubes, buena visibilidad",
            "efectos": "Condiciones normales de patrullaje",
            "velocidad_factor": 0.95,
            "color": "#87CEEB",
            "icono": "⛅"
        },
        "nublado": {
            "descripcion": "Cielo cubierto, visibilidad reducida",
            "efectos": "Precaución adicional requerida",
            "velocidad_factor": 0.9,
            "color": "#696969",
            "icono": "☁️"
        },
        "lluvia_ligera": {
            "descripcion": "Lluvia suave, calles húmedas",
            "efectos": "Velocidad reducida, mayor precaución",
            "velocidad_factor": 0.8,
            "color": "#4682B4",
            "icono": "🌦️"
        },
        "lluvia_intensa": {
            "descripcion": "Lluvia fuerte, visibilidad limitada",
            "efectos": "Patrullaje de emergencia únicamente",
            "velocidad_factor": 0.6,
            "color": "#191970",
            "icono": "🌧️"
        },
        "tormenta": {
            "descripcion": "Tormenta eléctrica, condiciones peligrosas",
            "efectos": "Patrullaje suspendido temporalmente",
            "velocidad_factor": 0.4,
            "color": "#8B008B",
            "icono": "⛈️"
        },
        "niebla": {
            "descripcion": "Niebla densa, visibilidad muy limitada",
            "efectos": "Velocidad muy reducida, luces encendidas",
            "velocidad_factor": 0.5,
            "color": "#708090",
            "icono": "🌫️"
        },
        "viento": {
            "descripcion": "Vientos fuertes, posibles obstáculos",
            "efectos": "Atención a objetos voladores",
            "velocidad_factor": 0.85,
            "color": "#20B2AA",
            "icono": "💨"
        }
    }
    return detalles_clima.get(clima, detalles_clima["soleado"])

# Mostrar detalles del clima
detalles = obtener_detalles_clima(clima_seleccionado)

# Mostrar el estado del clima de manera más simple
st.sidebar.markdown(f"**Clima Actual:**")
st.sidebar.markdown(f"{detalles['icono']} {opciones_clima_simple[clima_seleccionado_idx]}")
st.sidebar.markdown(f"*{detalles['descripcion']}*")
st.sidebar.markdown(f"**Efecto:** {detalles['efectos']}")
st.sidebar.markdown(f"**Factor de velocidad:** {detalles['velocidad_factor']:.0%}")

# Velocidad base ajustada por condiciones
velocidad_base = 40
factor_trafico = 1.0

# Ajustar velocidad según tráfico
if "FULL TRÁFICO" in nivel_trafico or "MUCHO TRÁFICO" in nivel_trafico:
    factor_trafico = 0.6  # 60% de velocidad normal
elif "MEDIO TRÁFICO" in nivel_trafico:
    factor_trafico = 0.8  # 80% de velocidad normal
elif "POCO TRÁFICO" in nivel_trafico:
    factor_trafico = 1.2  # 120% de velocidad normal
elif "SIN TRÁFICO" in nivel_trafico:
    factor_trafico = 1.4  # 140% de velocidad normal

# Aplicar factor climático
velocidad_final = int(velocidad_base * factor_trafico * detalles['velocidad_factor'])

st.sidebar.markdown("---")
st.sidebar.subheader("🚗 Velocidad Calculada")
st.sidebar.markdown(f"""
<div style="
    background-color: #f0f0f0; 
    padding: 10px; 
    border-radius: 5px; 
    text-align: center;
">
    <h3 style="color: #333; margin: 0;">{velocidad_final} km/h</h3>
    <small style="color: #666;">
        Base: {velocidad_base} km/h × Tráfico: {factor_trafico:.1f} × Clima: {detalles['velocidad_factor']:.1f}
    </small>
</div>
""", unsafe_allow_html=True)

velocidad_kmh = velocidad_final

# Botón para iniciar/detener simulación
if 'simulacion_activa' not in st.session_state:
    st.session_state.simulacion_activa = False

if st.sidebar.button("🚀 Iniciar Simulación" if not st.session_state.simulacion_activa else "⏸️ Detener Simulación"):
    st.session_state.simulacion_activa = not st.session_state.simulacion_activa

# Función para crear icono de carro personalizado
def crear_icono_carro(color, direccion, id_patrulla):
    """
    Crea un icono SVG personalizado de un carro con dirección y color específicos
    """
    # Colores más vibrantes para los carros
    colores_carros = {
        'red': '#FF0000',
        'blue': '#0000FF', 
        'green': '#00FF00',
        'purple': '#800080',
        'orange': '#FFA500',
        'darkred': '#8B0000',
        'lightred': '#FFB6C1',
        'beige': '#F5F5DC',
        'darkblue': '#00008B',
        'darkgreen': '#006400'
    }
    
    color_hex = colores_carros.get(color, '#FF0000')
    
    # SVG del carro con rotación basada en la dirección
    svg_carro = f"""
    <svg width="40" height="40" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">
        <g transform="rotate({direccion} 20 20)">
            <!-- Cuerpo del carro -->
            <rect x="8" y="12" width="24" height="16" rx="3" fill="{color_hex}" stroke="#000" stroke-width="1"/>
            <!-- Parabrisas -->
            <rect x="10" y="14" width="8" height="6" rx="1" fill="#87CEEB" stroke="#000" stroke-width="0.5"/>
            <!-- Ventana trasera -->
            <rect x="22" y="14" width="8" height="6" rx="1" fill="#87CEEB" stroke="#000" stroke-width="0.5"/>
            <!-- Ruedas -->
            <circle cx="12" cy="30" r="3" fill="#000"/>
            <circle cx="28" cy="30" r="3" fill="#000"/>
            <circle cx="12" cy="10" r="3" fill="#000"/>
            <circle cx="28" cy="10" r="3" fill="#000"/>
            <!-- Luces delanteras -->
            <circle cx="8" cy="16" r="1.5" fill="#FFFF00"/>
            <circle cx="8" cy="24" r="1.5" fill="#FFFF00"/>
            <!-- Número de patrulla -->
            <text x="20" y="22" text-anchor="middle" font-family="Arial" font-size="8" font-weight="bold" fill="#FFF">{id_patrulla}</text>
        </g>
    </svg>
    """
    
    return svg_carro

# Función para generar posición aleatoria dentro del área de Tacna
def generar_posicion_aleatoria():
    # Área aproximada de Tacna (coordenadas límites)
    lat_min, lat_max = -18.10, -17.93
    lon_min, lon_max = -70.35, -70.15
    
    lat = random.uniform(lat_min, lat_max)
    lon = random.uniform(lon_min, lon_max)
    return [lat, lon]

# Función para calcular nueva posición basada en velocidad y tiempo
def calcular_nueva_posicion(lat, lon, direccion, velocidad_kmh, tiempo_segundos):
    # Convertir velocidad a m/s
    velocidad_ms = velocidad_kmh * 1000 / 3600
    
    # Calcular distancia recorrida
    distancia_m = velocidad_ms * tiempo_segundos
    
    # Convertir distancia a grados (aproximación)
    # 1 grado de latitud ≈ 111,000 metros
    # 1 grado de longitud ≈ 111,000 * cos(latitud) metros
    delta_lat = (distancia_m * math.cos(math.radians(direccion))) / 111000
    delta_lon = (distancia_m * math.sin(math.radians(direccion))) / (111000 * math.cos(math.radians(lat)))
    
    nueva_lat = lat + delta_lat
    nueva_lon = lon + delta_lon
    
    # Mantener las patrullas dentro del área de Tacna
    nueva_lat = max(-18.10, min(-17.93, nueva_lat))
    nueva_lon = max(-70.35, min(-70.15, nueva_lon))
    
    return [nueva_lat, nueva_lon]

# Inicializar patrullas en session_state
if 'patrullas' not in st.session_state or len(st.session_state.patrullas) != num_patrullas:
    st.session_state.patrullas = []
    for i in range(num_patrullas):
        st.session_state.patrullas.append({
            'id': i + 1,
            'posicion': generar_posicion_aleatoria(),
            'direccion': random.uniform(0, 360),  # Dirección en grados
            'color': random.choice(['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'lightred', 'beige', 'darkblue', 'darkgreen']),
            'velocidad_actual': velocidad_kmh,
            'rastro': []  # Para guardar el rastro de movimiento
        })

# Crear el mapa base con mejor estilo
m = folium.Map(
    location=TACNA_CENTER,
    zoom_start=13,
    tiles="OpenStreetMap"
)

# Añadir marcadores para cada patrulla con iconos personalizados
for patrulla in st.session_state.patrullas:
    # Crear icono personalizado del carro
    icono_svg = crear_icono_carro(patrulla['color'], patrulla['direccion'], patrulla['id'])
    
    # Crear marcador con icono personalizado
    folium.Marker(
        location=patrulla['posicion'],
        popup=f"""
        <div style="width: 200px;">
            <h4>🚔 Patrulla {patrulla['id']}</h4>
            <p><b>Velocidad:</b> {patrulla['velocidad_actual']} km/h</p>
            <p><b>Dirección:</b> {patrulla['direccion']:.1f}°</p>
            <p><b>Color:</b> {patrulla['color'].title()}</p>
            <p><b>Coordenadas:</b><br>
               Lat: {patrulla['posicion'][0]:.4f}<br>
               Lon: {patrulla['posicion'][1]:.4f}</p>
        </div>
        """,
        tooltip=f"Patrulla {patrulla['id']} - {patrulla['color'].title()}",
        icon=folium.DivIcon(
            html=icono_svg,
            icon_size=(40, 40),
            icon_anchor=(20, 20)
        )
    ).add_to(m)
    
    # Agregar rastro de movimiento si existe
    if len(patrulla['rastro']) > 1:
        folium.PolyLine(
            locations=patrulla['rastro'],
            color=patrulla['color'],
            weight=2,
            opacity=0.6,
            popup=f"Rastro Patrulla {patrulla['id']}"
        ).add_to(m)

# Añadir un marcador para el centro de Tacna
folium.Marker(
    location=TACNA_CENTER,
    popup="📍 Centro de Tacna",
    tooltip="Centro de Tacna",
    icon=folium.Icon(color='black', icon='star', prefix='fa')
).add_to(m)

# Mostrar el mapa
st.subheader(f"🗺️ Mapa en tiempo real - {num_patrullas} Patrullas Activas")

# Mostrar información contextual
col_info1, col_info2, col_info3 = st.columns(3)

with col_info1:
    st.markdown(f"""
    <div style="background-color: {color_trafico}20; border-left: 4px solid {color_trafico}; padding: 10px; border-radius: 5px;">
        <h4 style="color: {color_trafico}; margin: 0;">{nivel_trafico}</h4>
        <p style="margin: 0; font-size: 12px; color: #666;">Hora: {hora_seleccionada.strftime('%H:%M')}</p>
    </div>
    """, unsafe_allow_html=True)

with col_info2:
    st.markdown(f"""
    <div style="background-color: {detalles['color']}20; border-left: 4px solid {detalles['color']}; padding: 10px; border-radius: 5px;">
        <h4 style="color: {detalles['color']}; margin: 0;">{detalles['icono']} {opciones_clima_simple[clima_seleccionado_idx]}</h4>
        <p style="margin: 0; font-size: 12px; color: #666;">Factor: {detalles['velocidad_factor']:.0%}</p>
    </div>
    """, unsafe_allow_html=True)

with col_info3:
    st.markdown(f"""
    <div style="background-color: #f0f0f0; border-left: 4px solid #333; padding: 10px; border-radius: 5px;">
        <h4 style="color: #333; margin: 0;">🚗 {velocidad_kmh} km/h</h4>
        <p style="margin: 0; font-size: 12px; color: #666;">Velocidad Actual</p>
    </div>
    """, unsafe_allow_html=True)

# Agregar controles adicionales
col_control1, col_control2, col_control3 = st.columns(3)

with col_control1:
    actualizar_automatico = st.checkbox("🔄 Actualización Automática", value=True)

with col_control2:
    mostrar_rastro = st.checkbox("📍 Mostrar Rastro", value=True)

with col_control3:
    intervalo_actualizacion = st.slider("⏱️ Intervalo (seg)", 1, 10, 3)

# Contenedor para el mapa con key única para evitar parpadeo
map_container = st.container()
with map_container:
    map_data = st_folium(
        m, 
        width=1200, 
        height=600, 
        returned_objects=["last_object_clicked"],
        key=f"mapa_{int(time.time())}"  # Key única para evitar parpadeo
    )

# Panel de información
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Patrullas Activas", num_patrullas)

with col2:
    st.metric("Velocidad Promedio", f"{velocidad_kmh} km/h")

with col3:
    status = "🟢 Activa" if st.session_state.simulacion_activa else "🔴 Inactiva"
    st.metric("Simulación", status)

# Información adicional del contexto
st.subheader("🌍 Condiciones Ambientales")
col_amb1, col_amb2 = st.columns(2)

with col_amb1:
    st.markdown(f"""
    **🚦 Estado del Tráfico:**
    - {descripcion_trafico}
    - Factor de velocidad por tráfico: {factor_trafico:.1f}x
    - Hora actual: {hora_seleccionada.strftime('%H:%M')}
    """)

with col_amb2:
    st.markdown(f"""
    **🌤️ Condiciones Climáticas:**
    - {detalles['descripcion']}
    - {detalles['efectos']}
    - Factor de velocidad por clima: {detalles['velocidad_factor']:.0%}
    """)

# Información detallada de las patrullas
st.subheader("📊 Estado de las Patrullas")

# Crear tabla de estado más visual
col_tabla1, col_tabla2 = st.columns(2)

with col_tabla1:
    for i, patrulla in enumerate(st.session_state.patrullas):
        if i % 2 == 0:  # Patrullas pares en la primera columna
            with st.expander(f"🚔 Patrulla {patrulla['id']} - {patrulla['color'].title()}", expanded=False):
                col_info1, col_info2 = st.columns(2)
                with col_info1:
                    st.metric("Latitud", f"{patrulla['posicion'][0]:.4f}")
                    st.metric("Velocidad", f"{patrulla['velocidad_actual']} km/h")
                with col_info2:
                    st.metric("Longitud", f"{patrulla['posicion'][1]:.4f}")
                    st.metric("Dirección", f"{patrulla['direccion']:.1f}°")
                
                # Barra de progreso para mostrar actividad
                if st.session_state.simulacion_activa:
                    st.progress(0.8, text="🚔 Patrullando activamente")
                else:
                    st.progress(0.2, text="⏸️ Estacionada")

with col_tabla2:
    for i, patrulla in enumerate(st.session_state.patrullas):
        if i % 2 == 1:  # Patrullas impares en la segunda columna
            with st.expander(f"🚔 Patrulla {patrulla['id']} - {patrulla['color'].title()}", expanded=False):
                col_info1, col_info2 = st.columns(2)
                with col_info1:
                    st.metric("Latitud", f"{patrulla['posicion'][0]:.4f}")
                    st.metric("Velocidad", f"{patrulla['velocidad_actual']} km/h")
                with col_info2:
                    st.metric("Longitud", f"{patrulla['posicion'][1]:.4f}")
                    st.metric("Dirección", f"{patrulla['direccion']:.1f}°")
                
                # Barra de progreso para mostrar actividad
                if st.session_state.simulacion_activa:
                    st.progress(0.8, text="🚔 Patrullando activamente")
                else:
                    st.progress(0.2, text="⏸️ Estacionada")

# Actualización automática si la simulación está activa
if st.session_state.simulacion_activa and actualizar_automatico:
    # Tiempo de actualización más frecuente para movimiento más fluido
    tiempo_transcurrido = intervalo_actualizacion  # Usar el slider
    
    for patrulla in st.session_state.patrullas:
        # Guardar posición anterior para el rastro
        if mostrar_rastro:
            patrulla['rastro'].append(patrulla['posicion'].copy())
            # Mantener solo las últimas 20 posiciones para el rastro
            if len(patrulla['rastro']) > 20:
                patrulla['rastro'].pop(0)
        
        # Calcular nueva posición
        nueva_posicion = calcular_nueva_posicion(
            patrulla['posicion'][0],
            patrulla['posicion'][1],
            patrulla['direccion'],
            patrulla['velocidad_actual'],
            tiempo_transcurrido
        )
        
        # Actualizar posición
        patrulla['posicion'] = nueva_posicion
        
        # Cambiar dirección ocasionalmente (15% de probabilidad)
        if random.random() < 0.15:
            patrulla['direccion'] = random.uniform(0, 360)
        
        # Variación leve en la velocidad para realismo
        if random.random() < 0.1:
            patrulla['velocidad_actual'] = max(30, min(50, velocidad_kmh + random.uniform(-5, 5)))
    
    # Refrescar la página con el intervalo seleccionado
    time.sleep(intervalo_actualizacion)
    st.rerun()

# Estadísticas adicionales
st.subheader("📈 Estadísticas del Sistema")
col_stats1, col_stats2, col_stats3, col_stats4 = st.columns(4)

with col_stats1:
    velocidad_promedio = sum(p['velocidad_actual'] for p in st.session_state.patrullas) / len(st.session_state.patrullas)
    st.metric("Velocidad Promedio", f"{velocidad_promedio:.1f} km/h")

with col_stats2:
    patrullas_activas = sum(1 for p in st.session_state.patrullas if st.session_state.simulacion_activa)
    st.metric("Patrullas en Movimiento", patrullas_activas)

with col_stats3:
    if st.session_state.simulacion_activa:
        st.metric("Tiempo de Simulación", f"{int(time.time() % 3600)} seg")
    else:
        st.metric("Estado", "Detenido")

with col_stats4:
    eficiencia = int(100 * factor_trafico * detalles['velocidad_factor'])
    st.metric("Eficiencia del Sistema", f"{eficiencia}%")

# Información adicional
st.sidebar.markdown("---")
st.sidebar.markdown("### ℹ️ Información del Sistema")
st.sidebar.markdown("""
- 🚔 **Patrullas**: Carros de policía personalizados
- 🎯 **Velocidad**: Calculada según tráfico y clima
- 🔄 **Actualización**: Movimiento fluido en tiempo real
- 📍 **Rastro**: Línea que muestra el recorrido
- 🎨 **Visual**: Iconos de carros con orientación
- 🌍 **Área**: Tacna, Perú
- ⏰ **Tráfico**: Varía según hora del día
- 🌤️ **Clima**: Afecta velocidad y visibilidad
""")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🎮 Controles")
st.sidebar.markdown("""
- **Hora**: Selecciona hora para simular tráfico
- **Clima**: Elige condiciones climáticas
- **Patrullas**: Número de vehículos activos
- **Simulación**: Inicia/detiene movimiento
- **Rastro**: Muestra trayectoria
- **Intervalo**: Velocidad de actualización
""")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🚦 Horarios de Tráfico")
st.sidebar.markdown("""
- **6:30-8:00 AM**: 🔴 Full Tráfico
- **8:00-11:00 AM**: 🟡 Medio Tráfico  
- **11:00 AM-1:00 PM**: 🔴 Full Tráfico
- **1:00-5:00 PM**: 🟡 Medio Tráfico
- **5:00-8:00 PM**: 🟥 Mucho Tráfico
- **8:00-11:00 PM**: 🟢 Poco Tráfico
- **11:00 PM-6:30 AM**: 🔵 Sin Tráfico
""")

# Footer mejorado
st.markdown("---")
st.markdown(f"""
<div style="text-align: center; padding: 20px; background-color: #f0f0f0; border-radius: 10px;">
    <h3>🚔 Sistema de Patrullas Tacna</h3>
    <p><strong>Simulación en Tiempo Real</strong> | Desarrollado con Streamlit & Folium</p>
    <p>Versión 3.0 - Con Simulación de Tráfico y Clima</p>
    <div style="margin-top: 15px;">
        <span style="background-color: {color_trafico}20; color: {color_trafico}; padding: 5px 10px; border-radius: 15px; margin: 0 5px;">
            {nivel_trafico}
        </span>
        <span style="background-color: {detalles['color']}20; color: {detalles['color']}; padding: 5px 10px; border-radius: 15px; margin: 0 5px;">
            {detalles['icono']} {opciones_clima_simple[clima_seleccionado_idx]}
        </span>
    </div>
</div>
""", unsafe_allow_html=True)
