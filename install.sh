#!/bin/bash

echo "======================================"
echo "  INSTALADOR DEL SISTEMA DE RUTEO"
echo "======================================"
echo

echo "Verificando Python..."
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 no está instalado"
    echo "Por favor instala Python 3.8 o superior"
    exit 1
fi

python3 --version

echo
echo "Actualizando pip..."
python3 -m pip install --upgrade pip

echo
echo "Instalando dependencias..."
pip3 install -r requirements.txt

echo
echo "======================================"
echo "  INSTALACIÓN COMPLETADA"
echo "======================================"
echo
echo "Para ejecutar el sistema:"
echo "  streamlit run sistema_experto_emergencias_fixed.py"

