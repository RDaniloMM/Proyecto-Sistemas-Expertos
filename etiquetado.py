# ==========================================================
#      CELDA 1: PREPARACIÓN Y GRAFO BASE
# ==========================================================
print("Importando librerías...")

import osmnx as ox
import networkx as nx
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.colors as mcolors
from IPython.display import display

print("\nLibrerías importadas correctamente.")

place_name = "Tacna, Peru"
print(f"\nDescargando la red vial de {place_name}...")
try:
    G = ox.graph_from_place(place_name, network_type='drive', simplify=True)
    print(f"\n¡Grafo base de Tacna creado exitosamente!")
    print(f"Número de nodos: {G.number_of_nodes()}, Número de arcos: {G.number_of_edges()}")
except Exception as e:
    print(f"Error al descargar el grafo: {e}.")

# =====================================================================
#    CELDA 2 (CORREGIDA): IDENTIFICACIÓN DE ZONAS DE INTERÉS
# =====================================================================
print("Identificando zonas y características de riesgo en Tacna...")

# --- 1. Identificar Puntos de Interés (POIs) ---
tags = {
    "colegios": {"amenity": ["school", "college", "university"]},
    "hospitales": {"amenity": ["hospital", "clinic"]},
    "mercados": {"amenity": ["marketplace"], "shop": ["market"]}
}
pois = {}
for key, tag_dict in tags.items():
    try:
        pois[key] = ox.features_from_place(place_name, tags=tag_dict)
        print(f"Se encontraron {len(pois[key])} {key}.")
    except:
        print(f"No se encontraron datos para {key}.")
        pois[key] = None

# --- 2. Simular y etiquetar calles en "mal estado" ---
for u, v, data in G.edges(data=True):
    data['mal_estado'] = False
    htype = data.get('highway', 'residential')
    # Manejar el caso de que 'htype' sea una lista
    if isinstance(htype, list):
        htype = htype[0]
    if htype in ['residential', 'unclassified'] and np.random.rand() < 0.05:
        data['mal_estado'] = True

# --- 3. Identificar intersecciones sin semáforo (simulado) ---
nodes_sin_semaforo = set()
for node, node_data in G.nodes(data=True):
    # Verificamos si el nodo en sí no es un semáforo
    if not node_data.get('highway') == 'traffic_signals':
        street_types = []
        # Iteramos por las calles que llegan al nodo
        for u, v, edge_data in G.edges(node, data=True):
            htype = edge_data.get('highway', 'residential')
            # Si el tipo de vía es una lista, tomamos el primer elemento.
            if isinstance(htype, list):
                street_types.append(htype[0])
            else:
                street_types.append(htype)

        # Convertimos la lista de tipos de calle a un set para ver los tipos únicos
        unique_street_types = set(street_types)

        # Si se cruzan más de un tipo de calle y todas son de bajo nivel, es un cruce sin semáforo
        if len(unique_street_types) > 1 and all(s in ['residential', 'tertiary', 'unclassified'] for s in unique_street_types):
            nodes_sin_semaforo.add(node)

# Etiquetamos los arcos que llegan a estas intersecciones
for u, v, data in G.edges(data=True):
    data['cruce_sin_semaforo'] = v in nodes_sin_semaforo

print(f"\nSe simularon {sum(d['mal_estado'] for u,v,d in G.edges(data=True))} calles en mal estado.")
print(f"Se identificaron {len(nodes_sin_semaforo)} intersecciones sin semáforo.")
print("\n--- Identificación de Zonas Completada ---")

# =====================================================================
#    CELDA 3: ETIQUETADO FINAL CON LAS 7 REGLAS
# =====================================================================

def get_risk_attributes(edge_data, G):
    """
    Aplica las 7 reglas del documento para calcular mu y sigma.
    """
    # Valores por defecto para una calle "normal"
    velocidad_kmh = 50.0
    penalizacion_tiempo = 1.0
    sigma_segundos = 10.0
    tipo_de_riesgo = "Ninguno"

    distancia_m = edge_data.get('length', 0)
    # u es el nodo de origen del arco, lo usamos para chequear proximidad a POIs
    u = edge_data['u']

    # --- LÓGICA DE LAS 7 REGLAS (APLICADAS EN ORDEN DE PRIORIDAD) ---

    # Regla 4: Zonas Escolares (Máxima prioridad)
    if 'colegios' in pois and pois['colegios'] is not None:
        # Chequeamos si el nodo de inicio del arco está dentro del área de influencia de algún colegio
        # Usamos G.nodes[u].get('geometry') por si algún nodo no tuviera geometría.
        node_geom = G.nodes[u].get('geometry')
        if node_geom and node_geom.within(pois['colegios'].unary_union.buffer(150)):
            tipo_de_riesgo, penalizacion_tiempo, sigma_segundos = "Zona Escolar", np.random.uniform(2.0, 3.5), 60

    # Regla 1: Mercados y Zonas Comerciales
    if tipo_de_riesgo == "Ninguno" and 'mercados' in pois and pois['mercados'] is not None:
        node_geom = G.nodes[u].get('geometry')
        if node_geom and node_geom.within(pois['mercados'].unary_union.buffer(250)):
            tipo_de_riesgo, penalizacion_tiempo, sigma_segundos = "Mercado/Comercio", np.random.uniform(1.7, 2.5), 50

    # Regla 5: Vías en Mal Estado
    if tipo_de_riesgo == "Ninguno" and edge_data['mal_estado']:
        tipo_de_riesgo, velocidad_kmh, penalizacion_tiempo, sigma_segundos = "Vía en Mal Estado", 30, np.random.uniform(1.8, 3.0), 70

    # Regla 6: Alrededores de Hospitales
    if tipo_de_riesgo == "Ninguno" and 'hospitales' in pois and pois['hospitales'] is not None:
        node_geom = G.nodes[u].get('geometry')
        if node_geom and node_geom.within(pois['hospitales'].unary_union.buffer(200)):
            tipo_de_riesgo, penalizacion_tiempo, sigma_segundos = "Zona Hospitalaria", np.random.uniform(1.25, 1.4), 35

    # Obtenemos el tipo de via, manejando el caso de que sea una lista
    htype = edge_data.get('highway', 'residential')
    if isinstance(htype, list):
        htype = htype[0]

    # Regla 2: Paraderos Informales (simulado en avenidas principales)
    if tipo_de_riesgo == "Ninguno" and htype in ['primary', 'secondary']:
        if np.random.rand() < 0.1: # 10% de probabilidad
            tipo_de_riesgo, penalizacion_tiempo, sigma_segundos = "Paradero Informal", np.random.uniform(1.4, 1.6), 40

    # Regla 3: Calles Angostas (simulado con tipo 'residential')
    if tipo_de_riesgo == "Ninguno" and htype == 'residential':
        tipo_de_riesgo, velocidad_kmh, penalizacion_tiempo, sigma_segundos = "Calle Angosta", 30, np.random.uniform(1.3, 1.5), 30

    # Regla 7: Cruces sin Semáforo
    if tipo_de_riesgo == "Ninguno" and edge_data['cruce_sin_semaforo']:
        tipo_de_riesgo, penalizacion_tiempo, sigma_segundos = "Cruce sin Semáforo", np.random.uniform(1.3, 1.7), 45

    # --- CÁLCULO FINAL DE MU Y SIGMA ---
    velocidad_mps = velocidad_kmh * 1000 / 3600
    mu_segundos = (distancia_m / velocidad_mps) * penalizacion_tiempo

    return tipo_de_riesgo, mu_segundos, sigma_segundos

# --- Aplicar la función a todo el grafo ---
print("Aplicando las 7 reglas de negocio para etiquetar cada arco...")
# Primero, asegurémonos de que cada arco tenga su 'u' y 'v' para que la función pueda usarlos
for u, v, data in G.edges(data=True):
    data['u'], data['v'] = u, v

# Ahora aplicamos la función de etiquetado
for u, v, data in G.edges(data=True):
    tipo_riesgo, mu, sigma = get_risk_attributes(data, G)
    data['tipo_de_riesgo'] = tipo_riesgo
    data['mu'] = mu
    data['sigma'] = sigma

print("\n¡Grafo final etiquetado según las 7 reglas!")
print("\n--- Etiquetado de Fase 2 Completado ---")
