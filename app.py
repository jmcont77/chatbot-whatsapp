from flask import Flask, request
from groq import Groq
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import os
import PyPDF2

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

# ==================== CARGA DE CONTEXTO LEGAL PDF ====================

# Variable global para el contenido del PDF
CONTEXTO_PDF = ""

def cargar_pdf(ruta_pdf):
    """Lee un PDF y extrae todo su texto"""
    try:
        texto_completo = ""
        
        with open(ruta_pdf, 'rb') as archivo:
            lector_pdf = PyPDF2.PdfReader(archivo)
            num_paginas = len(lector_pdf.pages)
            
            print(f"📄 Leyendo PDF: {ruta_pdf}")
            print(f"📊 Total de páginas: {num_paginas}")
            
            for num_pagina in range(num_paginas):
                pagina = lector_pdf.pages[num_pagina]
                texto_pagina = pagina.extract_text()
                
                if texto_pagina:
                    texto_completo += texto_pagina + "\n\n"
            
            print(f"✅ PDF cargado: {len(texto_completo):,} caracteres extraídos")
            return texto_completo.strip()
            
    except FileNotFoundError:
        print(f"❌ No se encontró el archivo {ruta_pdf}")
        return ""
    except Exception as e:
        print(f"❌ Error leyendo PDF: {e}")
        return ""

# Cargar PDF al iniciar (busca "contexto.pdf" en el directorio)
PDF_PATH = os.path.join(os.path.dirname(__file__), 'contexto.pdf')

if os.path.exists(PDF_PATH):
    CONTEXTO_PDF = cargar_pdf(PDF_PATH)
    if CONTEXTO_PDF:
        print(f"✅ Contexto legal PDF cargado exitosamente")
    else:
        print(f"⚠️ PDF encontrado pero vacío")
else:
    print(f"⚠️ No se encontró 'contexto.pdf'")
    print(f"ℹ️ El bot funcionará sin contexto legal adicional")

# ==================== FIN CARGA PDF ====================

def responder_con_ia(mensaje_usuario, telefono):
    """Genera respuesta usando Groq con contexto de conversación y conocimiento legal"""
    try:
        # Obtener o crear historial de conversación
        if telefono not in conversaciones:
            conversaciones[telefono] = []
        
        # Agregar mensaje del usuario al historial
        conversaciones[telefono].append({
            "role": "user",
            "content": mensaje_usuario
        })
        
        # Construir prompt del sistema especializado en fondos de empleados
        prompt_sistema = """Eres AnalfeAmigo, un asistente legal especializado que trabaja para ANALFE, entidad que presta servicios de asesoría a fondos de empleados en Colombia.

TU MISIÓN:
- Responder preguntas legales sobre la operación de fondos de empleados en Colombia
- Proporcionar información precisa basada en la normativa colombiana
- Orientar sobre procedimientos, requisitos legales y mejores prácticas
- Ser profesional, claro y conciso

ALCANCE:
- Fondos de empleados en Colombia
- Marco legal colombiano (Leyes, Decretos, Resoluciones)
- Operación, constitución, administración
- Aspectos tributarios, contables y financieros
- Derechos y deberes de asociados

ESTILO:
- Profesional pero cercano
- Respuestas claras y estructuradas
- Cita artículos o normativa cuando sea relevante
- Máximo 4-5 oraciones por respuesta
- Si la consulta es compleja, sugiere contacto directo con ANALFE

IMPORTANTE:
- No des asesoría sobre casos específicos sin más contexto
- Si no tienes información suficiente, recomienda consultar con un asesor de ANALFE
- Siempre menciona que tus respuestas son orientativas"""
        
        # Si hay PDF con normativa, agregarlo al prompt
        if CONTEXTO_PDF:
            # Limitar a 4000 caracteres para no exceder límites de tokens
            contexto_limitado = CONTEXTO_PDF[:4000] + "..." if len(CONTEXTO_PDF) > 4000 else CONTEXTO_PDF
            
            prompt_sistema += f"""

DOCUMENTACIÓN LEGAL Y NORMATIVA DISPONIBLE:
{contexto_limitado}

INSTRUCCIONES PARA USO DE LA DOCUMENTACIÓN:
- USA la información anterior como base para tus respuestas
- Si la pregunta se relaciona con un artículo o norma en el documento, cítalo
- Si está en la documentación, da respuesta precisa basada en ella
- Si no está en la documentación pero es sobre fondos de empleados, usa tu conocimiento general de la normativa colombiana
- Siempre aclara si estás citando documentación específica o dando orientación general"""
        
        # Preparar mensajes para Groq (incluye sistema + historial)
        mensajes = [
            {
                "role": "system",
                "content": prompt_sistema
            }
        ] + conversaciones[telefono][-10:]  # Solo últimos 10 mensajes
        
        # Llamar a Groq con temperatura más baja para respuestas legales más precisas
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=mensajes,
            temperature=0.5,  # Más bajo para precisión legal
            max_tokens=300  # Un poco más para explicaciones legales
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
    return {
        "status": "ok",
        "message": "AnalfeAmigo - Bot de asesoría legal funcionando",
        "servicio": "Fondos de empleados Colombia",
        "contexto_pdf_cargado": len(CONTEXTO_PDF) > 0,
        "contexto_caracteres": len(CONTEXTO_PDF)
    }, 200

@app.route('/', methods=['GET'])
def home():
    """Página de inicio"""
    pdf_status = "✅ Cargado" if CONTEXTO_PDF else "❌ No cargado"
    pdf_caracteres = f"{len(CONTEXTO_PDF):,} caracteres" if CONTEXTO_PDF else "N/A"
    
    return f"""
    <h1>⚖️ AnalfeAmigo - Asistente Legal</h1>
    <h2>ANALFE - Servicios para Fondos de Empleados</h2>
    <p>Bot de asesoría legal para fondos de empleados en Colombia 🇨🇴</p>
    <hr>
    <p><strong>Estado:</strong> ✅ Funcionando correctamente</p>
    <p><strong>Plataforma:</strong> Twilio WhatsApp</p>
    <p><strong>IA:</strong> Groq (llama-3.3-70b-versatile)</p>
    <hr>
    <p><strong>Documentación Legal:</strong> {pdf_status}</p>
    <p><strong>Tamaño:</strong> {pdf_caracteres}</p>
    <hr>
    <p><strong>Endpoints:</strong></p>
    <ul>
        <li><code>/webhook</code> - Recibe mensajes de WhatsApp</li>
        <li><code>/health</code> - Estado del servidor</li>
    </ul>
    <hr>
    <p><strong>Especialización:</strong></p>
    <ul>
        <li>Normativa de fondos de empleados</li>
        <li>Constitución y operación</li>
        <li>Aspectos legales y tributarios</li>
        <li>Derechos de asociados</li>
        <li>Procedimientos administrativos</li>
    </ul>
    """, 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)