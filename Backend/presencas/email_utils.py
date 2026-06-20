import os
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

def enviar_email_brevo(destino, assunto, mensagem):
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = os.getenv("BREVO_API_KEY")

    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )

    email = sib_api_v3_sdk.SendSmtpEmail(
        sender={"name": "FaceTrack", "email": os.getenv("EMAIL_FROM")},
        to=[{"email": destino}],
        subject=assunto,
        text_content=mensagem
    )

    try:
        api_instance.send_transac_email(email)
        return True
    except ApiException as e:
        print("Erro Brevo:", e)
        return False