import streamlit as st
import json
import sqlite3
import datetime

def callback_handler():
    """Maneja los callbacks del frontend JavaScript para operaciones de base de datos"""
    
    # Verificar si hay datos del callback en query params
    query_params = st.experimental_get_query_params()
    
    if 'callback_data' in query_params:
        try:
            # Decodificar datos del callback
            callback_data = json.loads(query_params['callback_data'][0])
            callback_type = callback_data.get('type')
            data = callback_data.get('data', {})
            
            if callback_type == 'registrar_incidente':
                # Registrar incidente en base de datos
                incidente_id = registrar_incidente_callback(data)
                st.success(f"✅ Incidente {incidente_id} registrado exitosamente")
                
                # Limpiar query params
                st.experimental_set_query_params()
                
            elif callback_type == 'actualizar_patrulla':
                # Actualizar estado de patrulla
                actualizar_patrulla_callback(data)
                st.success(f"✅ Patrulla {data.get('patrulla_id')} actualizada")
                
        except Exception as e:
            st.error(f"❌ Error en callback: {str(e)}")

def registrar_incidente_callback(data):
    """Registra un incidente desde el callback del frontend"""
    conn = sqlite3.connect("incidentes_emergencia.db")
    cursor = conn.cursor()
    
    fecha_actual = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        INSERT INTO incidentes (nodo_incidente, latitud, longitud, fecha_hora, patrulla_asignada, tipo_ruta, estado)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('nodo_incidente'),
        data.get('latitud'),
        data.get('longitud'),
        fecha_actual,
        data.get('patrulla_asignada'),
        data.get('tipo_ruta'),
        'asignado'
    ))
    
    incidente_id = cursor.lastrowid
    
    # También registrar la misión de patrulla
    if data.get('patrulla_asignada') and data.get('ruta_calculada'):
        ruta_json = json.dumps(data.get('ruta_calculada'))
        
        cursor.execute('''
            INSERT INTO historial_patrullas 
            (patrulla_id, incidente_id, nodo_origen, nodo_destino, ruta_calculada, tipo_ruta, fecha_asignacion, estado_final)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('patrulla_asignada'),
            incidente_id,
            data.get('nodo_origen', 0),  # Se podría obtener del estado de la patrulla
            data.get('nodo_incidente'),
            ruta_json,
            data.get('tipo_ruta'),
            fecha_actual,
            'asignado'
        ))
    
    conn.commit()
    conn.close()
    
    return incidente_id

def actualizar_patrulla_callback(data):
    """Actualiza el estado de una patrulla desde el callback del frontend"""
    # Aquí se podría actualizar el estado de la patrulla en session_state
    # o en una base de datos de patrullas si se implementara
    pass

# Función para generar JavaScript de comunicación
def generar_js_comunicacion():
    """Genera el JavaScript necesario para la comunicación con Streamlit"""
    return """
    <script>
    // Función para enviar datos a Streamlit
    function enviarDatosAStreamlit(tipo, datos) {
        const callbackData = {
            type: tipo,
            data: datos
        };
        
        // Crear URL con query params
        const url = new URL(window.location);
        url.searchParams.set('callback_data', JSON.stringify(callbackData));
        
        // Recargar la página con los nuevos params
        window.location.href = url.toString();
    }
    
    // Sobrescribir la función asignarPatrulla para incluir guardado en BD
    const asignarPatrullaOriginal = window.asignarPatrulla;
    window.asignarPatrulla = function(idPatrulla, tipoRuta) {
        // Ejecutar lógica original
        if (asignarPatrullaOriginal) {
            asignarPatrullaOriginal(idPatrulla, tipoRuta);
        }
        
        // Preparar datos para enviar a Streamlit
        const rutaSeleccionada = tipoRuta === 'rapida' ? rutaRapida : rutaSegura;
        const datosIncidente = {
            nodo_incidente: nodoDestino,
            latitud: marcadorIncidente ? marcadorIncidente.getLatLng().lat : 0,
            longitud: marcadorIncidente ? marcadorIncidente.getLatLng().lng : 0,
            patrulla_asignada: idPatrulla,
            tipo_ruta: tipoRuta,
            ruta_calculada: rutaSeleccionada ? rutaSeleccionada.path : []
        };
        
        // Enviar a Streamlit después de un breve delay
        setTimeout(() => {
            console.log('📝 Enviando datos de incidente a Streamlit:', datosIncidente);
            enviarDatosAStreamlit('registrar_incidente', datosIncidente);
        }, 2000); // 2 segundos de delay para que el usuario vea la confirmación
    };
    
    console.log('🔗 Sistema de comunicación con Streamlit activado');
    </script>
    """
