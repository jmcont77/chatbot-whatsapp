from flask import Flask, request
from groq import Groq
import requests
import os

app = Flask(__name__)
groq_client = Groq(api_key=os.getenv('GROQ_API_KEY'))

# Configuración Ultramsg
ULTRAMSG_INSTANCE = os.getenv('ULTRAMSG_INSTANCE')
ULTRAMSG_TOKEN = os.getenv('ULTRAMSG_TOKEN')

conversaciones = {}

def enviar_mensaje(telefono, mensaje):
    """Envía mensaje por WhatsApp usando Ultramsg"""
    url = f"https://api.ultramsg.com/{ULTRAMSG_INSTANCE}/messages/chat"
    payload = {
        "token": ULTRAMSG_TOKEN,
        "to": telefono,
        "body": mensaje
    }
    try:
        response = requests.post(url, data=payload)
        return response.json()
    except Exception as e:
        print(f"Error enviando mensaje: {e}")
        return None

def responder_con_ia(mensaje_usuario):
    """Genera respuesta usando Groq"""
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "Eres un asistente amable para agendar citas médicas por WhatsApp. Responde en español de forma breve y profesional. Si te preguntan por citas disponibles, di que pronto tendrás esa función. Por ahora solo saluda y ayuda con consultas generales."
                },
                {
                    "role": "user",
                    "content": mensaje_usuario
                }
            ],
            temperature=0.7,
            max_tokens=200
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error con Groq: {e}")
        return "Disculpa, tuve un problema. ¿Puedes repetir?"

@app.route('/webhook', methods=['POST'])
def webhook():
    """Recibe mensajes de Ultramsg"""
    data = request.get_json()
    
    if not data:
        return {"status": "no data"}, 200
    
    # Extraer datos del mensaje
    mensaje = data.get('data', {}).get('body', '')
    telefono = data.get('data', {}).get('from', '')
    
    if not mensaje or not telefono:
        return {"status": "missing data"}, 200
    
    # Generar respuesta con IA
    respuesta = responder_con_ia(mensaje)
    
    # Enviar respuesta
    enviar_mensaje(telefono, respuesta)
    
    return {"status": "success"}, 200

@app.route('/health', methods=['GET'])
def health():
    return {"status": "ok"}, 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
