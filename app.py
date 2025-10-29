from flask import Flask, request
from groq import Groq
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import os

app = Flask(__name__)

# Configuración Groq
groq_client = Groq(api_key=os.getenv('GROQ_API_KEY'))

# Configuración Twilio
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER')

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Historial de conversaciones (en memoria)
conversaciones = {}

def responder_con_ia(mensaje_usuario, telefono):
    """Genera respuesta usando Groq con contexto de conversación"""
    try:
        # Obtener o crear historial de conversación
        if telefono not in conversaciones:
            conversaciones[telefono] = []
        
        # Agregar mensaje del usuario al historial
        conversaciones[telefono].append({
            "role": "user",
            "content": mensaje_usuario
        })
        
        # Preparar mensajes para Groq (incluye sistema + historial)
        mensajes = [
            {
                "role": "system",
                "content": "Eres un asistente amable para agendar citas médicas por WhatsApp. Responde en español de forma breve y profesional (máximo 2-3 oraciones). Si te preguntan por citas disponibles, di que pronto tendrás esa función. Por ahora solo saluda y ayuda con consultas generales."
            }
        ] + conversaciones[telefono][-10:]  # Solo últimos 10 mensajes para no exceder límites
        
        # Llamar a Groq
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=mensajes,
            temperature=0.7,
            max_tokens=200
        )
        
        respuesta = response.choices[0].message.content.strip()
        
        # Agregar respuesta al historial
        conversaciones[telefono].append({
            "role": "assistant",
            "content": respuesta
        })
        
        return respuesta
        
    except Exception as e:
        print(f"Error con Groq: {e}")
        return "Disculpa, tuve un problema técnico. ¿Puedes intentar de nuevo?"

def enviar_mensaje(telefono, mensaje):
    """Envía mensaje por WhatsApp usando Twilio"""
    try:
        message = twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            body=mensaje,
            to=telefono
        )
        print(f"✅ Mensaje enviado: {message.sid}")
        return message.sid
    except Exception as e:
        print(f"❌ Error enviando mensaje: {e}")
        return None

@app.route('/webhook', methods=['POST'])
def webhook():
    """Recibe mensajes de Twilio WhatsApp"""
    try:
        # Extraer datos del mensaje de Twilio
        mensaje = request.form.get('Body', '').strip()
        telefono = request.form.get('From', '')  # Formato: whatsapp:+573001234567
        
        print(f"📨 Mensaje recibido de {telefono}: {mensaje}")
        
        if not mensaje or not telefono:
            print("⚠️ Mensaje o teléfono vacío")
            return str(MessagingResponse()), 200
        
        # Generar respuesta con IA
        respuesta = responder_con_ia(mensaje, telefono)
        print(f"🤖 Respuesta generada: {respuesta}")
        
        # Enviar respuesta usando Twilio
        enviar_mensaje(telefono, respuesta)
        
        return str(MessagingResponse()), 200
        
    except Exception as e:
        print(f"❌ Error en webhook: {e}")
        return str(MessagingResponse()), 500

@app.route('/health', methods=['GET'])
def health():
    """Endpoint de salud para verificar que el servidor funciona"""
    return {"status": "ok", "message": "Bot de WhatsApp con Twilio funcionando"}, 200

@app.route('/', methods=['GET'])
def home():
    """Página de inicio"""
    return """
    <h1>🤖 Chatbot WhatsApp con Twilio</h1>
    <p>El bot está funcionando correctamente.</p>
    <p>Endpoint de webhook: <code>/webhook</code></p>
    <p>Health check: <code>/health</code></p>
    """, 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)