# 🚔 Sistema de Patrullas en Tiempo Real - Tacna

## Mejoras Implementadas: Movimiento por Calles Reales

### 🎯 Objetivo
Hacer que las patrullas se muevan siguiendo exactamente las calles reales del mapa de Tacna, respetando las curvas, intersecciones y geometrías reales de las vías.

### 📋 Problemas Solucionados

#### 1. **Interpolación Linear vs Geometría Real**
**Problema Anterior:**
- Las patrullas se movían en línea recta entre nodos (intersecciones)
- No respetaban las curvas y formas reales de las calles
- Movimiento no realista que cortaba por edificios y espacios

**Solución Implementada:**
- Extracción de geometrías reales de cada calle usando OSMnx
- Movimiento por segmentos de la geometría real
- Interpolación a lo largo de los puntos que definen la forma de la calle

#### 2. **Datos de Geometría Mejorados**
**Mejoras:**
- Carga del grafo con `simplify=False` para obtener geometrías detalladas
- Procesamiento de coordenadas de geometría para cada arista
- Conversión de coordenadas de (lon, lat) a [lat, lon] para compatibilidad
- Fallback a interpolación simple si no hay geometría disponible

#### 3. **Algoritmo de Movimiento Avanzado**
**Características:**
- `moveAlongGeometry()`: Movimiento por geometría real
- `moveAlongSimplePath()`: Fallback para casos sin geometría
- Control de progreso por segmentos de geometría
- Manejo de direcciones (forward/reverse) según el camino calculado

### 🔧 Archivos Modificados

#### `realtime_map.py`
- **Función `cargar_grafo_tacna()`**: Carga grafo con geometrías detalladas
- **Función `generar_html_realtime()`**: Genera HTML con geometrías reales
- **JavaScript mejorado**: Algoritmos de movimiento por geometría real

### 📊 Funcionalidades Actuales

#### ✅ Implementadas
1. **Movimiento Real por Calles**
   - Patrullas siguen exactamente las calles del mapa
   - Respetan curvas, intersecciones y geometrías reales
   - Movimiento fluido sin "cortar" por edificios

2. **Visualización Mejorada**
   - Calles dibujadas con sus geometrías reales
   - Colores diferenciados por tipo de riesgo
   - Trayectorias de patrullas visibles

3. **Controles Avanzados**
   - Número de patrullas (1-10)
   - Hora del día (afecta velocidad por tráfico)
   - Condiciones climáticas (afecta velocidad)

4. **Tiempo Real**
   - Actualización cada segundo
   - Sin recargar la página
   - Movimiento fluido y continuo

#### 🎛️ Controles de Velocidad

**Factores que Afectan la Velocidad:**
- **Hora del día**: Hora pico (6-8, 17-19) reduce velocidad
- **Clima**: Lluvia y neblina reducen velocidad
- **Tipo de calle**: Diferentes velocidades por tipo de vía

### 🧮 Algoritmo de Movimiento

```javascript
// Movimiento por geometría real
moveAlongGeometry(patrulla, edge) {
    1. Obtener geometría real de la calle
    2. Calcular progreso en el segmento actual
    3. Interpolar posición en la geometría
    4. Avanzar por segmentos hasta completar la calle
    5. Pasar al siguiente nodo del camino
}
```

### 🎨 Visualización

#### Colores por Tipo de Riesgo:
- 🔴 **Rojo**: Calles con riesgo de accidentes (vías principales)
- 🟠 **Naranja**: Calles con riesgo de robos (residenciales)
- 🟡 **Amarillo**: Calles con riesgo de vandalismo (terciarias)
- 🔵 **Azul**: Otras calles

#### Elementos del Mapa:
- 🚔 **Patrullas**: Iconos de policía que se mueven
- 🟣 **Trayectorias**: Líneas púrpuras que muestran el recorrido
- 🗺️ **Calles**: Líneas coloreadas según tipo de riesgo

### 🚀 Ejecución

```bash
# Navegar al directorio
cd "d:\Proyectos\SE_Actualizado"

# Ejecutar la aplicación
python -m streamlit run realtime_map.py
uv run streamlit run realtime_map.py
```

### 📱 Uso

1. **Abrir la aplicación** en el navegador
2. **Configurar parámetros** en la barra lateral:
   - Número de patrullas
   - Hora del día
   - Condiciones climáticas
3. **Observar el movimiento** en tiempo real
4. **Analizar trayectorias** y patrones de movimiento

### 🔄 Próximas Mejoras

1. **Optimización de Rendimiento**
   - Cachear geometrías para mejorar velocidad
   - Optimizar cálculos de distancia
   - Reducir carga computacional

2. **Funcionalidades Adicionales**
   - Selección manual de rutas
   - Zonas de interés especiales
   - Alertas y notificaciones

3. **Visualización Avanzada**
   - Animaciones más suaves
   - Indicadores de velocidad
   - Historial de movimiento

### 💡 Notas Técnicas

- **OSMnx**: Usado para obtener datos reales de OpenStreetMap
- **Leaflet**: Biblioteca JavaScript para visualización de mapas
- **Streamlit**: Framework web para la interfaz
- **Dijkstra**: Algoritmo para cálculo de rutas más cortas

### 🎯 Resultado Final

El sistema ahora simula de manera realista el movimiento de patrullas policiales por las calles reales de Tacna, proporcionando una herramienta útil para:

- Análisis de patrones de patrullaje
- Optimización de rutas
- Simulación de diferentes escenarios
- Entrenamiento y planificación operacional

---

*Sistema desarrollado con enfoque en realismo y funcionalidad práctica para simulación de patrullas policiales.*
