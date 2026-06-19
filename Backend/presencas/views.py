import base64
import sqlite3
import face_recognition
import numpy as np
import cv2
import io
import datetime
import os
import json
from django.http import StreamingHttpResponse, JsonResponse
from django.conf import settings
from django.db import IntegrityError
from django.views.decorators.http import require_http_methods
from django.core.mail import send_mail
from django.utils import timezone
from PIL import Image
from functools import wraps
from django.shortcuts import render, redirect, get_object_or_404
from .models import FichaUtilizador, Presenca, PasswordResetToken
from django.views.decorators.csrf import csrf_exempt

def admin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if 'user_id' not in request.session:
            return redirect("login")
        if not request.session.get("is_admin", False):
            return redirect("home")
        return view_func(request, *args, **kwargs)
    return _wrapped

def login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        try:
            user = FichaUtilizador.objects.get(username=username)
            if user.check_password(password):
                request.session['user_id'] = user.id
                request.session['username'] = user.username
                request.session['is_admin'] = user.administrador
                return redirect("home")
            else:
                return render(request, "presencas/login.html", {"error": "Password incorreta"})
        except FichaUtilizador.DoesNotExist:
            return render(request, "presencas/login.html", {"error": "Username nÃ£o existe"})

    return render(request, "presencas/login.html")

def logout(request):
    request.session.flush()
    return redirect("login")

def recuperar_password(request):
    """Pagina inicial de recuperacao de palavra-passe - pedir email"""
    error = None
    success = None

    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        request.session.pop('reset_email', None)
        request.session.pop('reset_token_validado', None)
        request.session.pop('reset_token', None)

        try:
            user = FichaUtilizador.objects.filter(email__iexact=email).first()
            if not user:
                # Nao revelar se o email existe ou nao por seguranca
                success = "Se este email esta registado, recebera um codigo de recuperacao."
                return render(request, "presencas/recuperar_password.html", {
                    "error": error,
                    "success": success
                })

            # Criar token
            reset_token = PasswordResetToken.criar_token(user)

            # Enviar email
            assunto = "Recuperacao de Palavra-Passe - FaceTrack"
            mensagem = f"""
Ola {user.nome},

Recebeu um pedido para recuperar a sua palavra-passe.
Utilize o seguinte codigo para continuar (valido por 1 hora):

{reset_token.token}

Se nao solicitou este pedido, ignore este email.

Cumprimentos,
Equipa FaceTrack
            """

            try:
                send_mail(
                    assunto,
                    mensagem,
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False,
                )
                success = "Um email com o codigo de recuperacao foi enviado para o seu email."
                # Guardar o email na sessao para usar na proxima pagina
                request.session['reset_email'] = user.email
            except Exception as e:
                error = f"Erro ao enviar email: {str(e)}"
        except Exception:
            error = "Ocorreu um erro ao processar o pedido de recuperacao."

    return render(request, "presencas/recuperar_password.html", {
        "error": error,
        "success": success
    })

def validar_token(request):
    """Pagina para validar o codigo e so depois alterar a palavra-passe."""
    error = None
    success = None

    email = request.session.get('reset_email')
    if not email:
        return redirect("login")

    codigo_validado = bool(request.session.get('reset_token_validado'))

    if request.method == "POST":
        acao = request.POST.get("acao")

        if acao == "validar_codigo":
            token = (request.POST.get("token") or "").strip()
            if not token.isdigit() or len(token) != 6:
                error = "O codigo deve ter exatamente 6 digitos."
                return render(request, "presencas/validar_token.html", {
                    "error": error,
                    "success": success,
                    "email": email,
                    "codigo_validado": codigo_validado
                })
            try:
                reset_token = PasswordResetToken.objects.get(token=token)

                if not reset_token.is_valid():
                    error = "O codigo de recuperacao expirou. Solicite um novo."
                    request.session.pop('reset_email', None)
                    request.session.pop('reset_token_validado', None)
                    request.session.pop('reset_token', None)
                elif reset_token.user.email != email:
                    error = "Dados invalidos."
                else:
                    request.session['reset_token_validado'] = True
                    request.session['reset_token'] = reset_token.token
                    codigo_validado = True
                    success = "Codigo validado com sucesso. Pode agora alterar a palavra-passe."
            except PasswordResetToken.DoesNotExist:
                error = "Codigo de recuperacao invalido."

        elif acao == "alterar_password":
            if not codigo_validado:
                error = "Valide primeiro o codigo de recuperacao."
            else:
                nova_password = request.POST.get("nova_password")
                confirmar_password = request.POST.get("confirmar_password")

                if not nova_password or not confirmar_password:
                    error = "Preencha os campos da nova palavra-passe."
                elif nova_password != confirmar_password:
                    error = "As palavras-passe nao coincidem."
                else:
                    token_guardado = request.session.get('reset_token')
                    try:
                        reset_token = PasswordResetToken.objects.get(token=token_guardado)

                        if not reset_token.is_valid():
                            error = "O codigo de recuperacao expirou. Solicite um novo."
                            request.session.pop('reset_email', None)
                            request.session.pop('reset_token_validado', None)
                            request.session.pop('reset_token', None)
                        elif reset_token.user.email != email:
                            error = "Dados invalidos."
                        else:
                            reset_token.user.set_password(nova_password)
                            reset_token.delete()
                            request.session.pop('reset_email', None)
                            request.session.pop('reset_token_validado', None)
                            request.session.pop('reset_token', None)
                            return render(request, "presencas/recuperar_sucesso.html")
                    except PasswordResetToken.DoesNotExist:
                        error = "Codigo de recuperacao invalido."
        else:
            error = "Pedido invalido."

    return render(request, "presencas/validar_token.html", {
        "error": error,
        "success": success,
        "email": email,
        "codigo_validado": codigo_validado
    })

def home(request):
    if 'user_id' not in request.session:
        return redirect("login")
    return render(
        request,
        "presencas/home.html",
        {
            "username": request.session.get("username"),
            "is_admin": request.session.get("is_admin", False),
        },
    )

def presencas(request):
    # redirect to the named login url (typo corrected)
    if 'user_id' not in request.session:
        return redirect("login")
    
    # Obter todas as presenÃ§as ordenadas por data/hora descrescente
    from .models import Presenca
    from django.db.models import Q
    
    todas_presencas = Presenca.objects.all().order_by('-data_hora')
    
    # Aplicar filtros
    filtro_dia = request.GET.get('filtro_dia', '')
    filtro_utilizador = request.GET.get('filtro_utilizador', '')
    filtro_tipo = request.GET.get('filtro_tipo', '')
    
    if filtro_dia:
        # Filtrar por data (apenas a data, nÃ£o a hora)
        from datetime import datetime
        data_selecionada = datetime.strptime(filtro_dia, '%Y-%m-%d').date()
        todas_presencas = todas_presencas.filter(data_hora__date=data_selecionada)
    
    if filtro_utilizador:
        todas_presencas = todas_presencas.filter(user_id=filtro_utilizador)
    
    if filtro_tipo:
        todas_presencas = todas_presencas.filter(tipo=filtro_tipo)
    
    # Obter lista de utilizadores para o dropdown
    utilizadores = FichaUtilizador.objects.all().order_by('nome')
    
    return render(request, "presencas/presencas.html", {
        "username": request.session.get('username'),
        "presencas": todas_presencas,
        "utilizadores": utilizadores,
        "filtro_dia": filtro_dia,
        "filtro_utilizador": filtro_utilizador,
        "filtro_tipo": filtro_tipo,
    })
def presencas_utilizador(request):
    # redirect to the named login url (typo corrected)
    if 'user_id' not in request.session:
        return redirect("login")
    
    # Obter todas as presenÃ§as do utilizador logado ordenadas por data/hora descrescente
    from .models import Presenca
    
    user_id = request.session['user_id']
    todas_presencas = Presenca.objects.filter(user_id=user_id).order_by('-data_hora')
    
    # Aplicar filtros
    filtro_dia = request.GET.get('filtro_dia', '')
    filtro_tipo = request.GET.get('filtro_tipo', '')
    
    if filtro_dia:
        # Filtrar por data (apenas a data, nÃ£o a hora)
        from datetime import datetime
        data_selecionada = datetime.strptime(filtro_dia, '%Y-%m-%d').date()
        todas_presencas = todas_presencas.filter(data_hora__date=data_selecionada)
    
    if filtro_tipo:
        todas_presencas = todas_presencas.filter(tipo=filtro_tipo)
    
    return render(request, "presencas/presencas_utilizador.html", {
        "username": request.session.get('username'),
        "presencas": todas_presencas,
        "filtro_dia": filtro_dia,
        "filtro_tipo": filtro_tipo,
    })

def load_known_faces():
    registos = FichaUtilizador.objects.all()

    known_face_encodings = []
    known_face_names = []

    for user in registos:
        nome = user.nome
        caminho_imagem = user.imagem

        if not caminho_imagem:
            print(f"[!] Sem imagem: {nome}")
            continue

        caminho_completo = os.path.join(settings.MEDIA_ROOT, str(caminho_imagem))

        print("A verificar:", caminho_completo)

        if not os.path.isfile(caminho_completo):
            print(f"[!] Não existe: {caminho_completo}")
            continue

        image = face_recognition.load_image_file(caminho_completo)
        encodings = face_recognition.face_encodings(image)

        print(f"{nome} encodings:", len(encodings))

        if len(encodings) > 0:
            known_face_encodings.append(encodings[0])
            known_face_names.append(nome)

    print("TOTAL CARREGADO:", len(known_face_names))
    return known_face_encodings, known_face_names

# Carregar rostos uma vez
try:
    KNOWN_FACE_ENCODINGS, KNOWN_FACE_NAMES = load_known_faces()
except Exception:
    KNOWN_FACE_ENCODINGS = []
    KNOWN_FACE_NAMES = []


# VariÃ¡vel global para armazenar o rosto detetado atualmente
current_detected_person = None
@csrf_exempt
@require_http_methods(["POST"])
def gen_frames(request):
    data = json.loads(request.body or "{}")
    image_data = data.get("image")

    if not image_data:
        return JsonResponse({"error": "No image provided"}, status=400)

    try:
        image_data = image_data.split(",")[1]
        img_bytes = base64.b64decode(image_data)

        np_arr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        face_locations = face_recognition.face_locations(rgb)
        face_encodings = face_recognition.face_encodings(rgb, face_locations)

        name = "Desconhecido"

        # 🔥 DEBUG IMPORTANTE
        print("Faces encontradas:", len(face_encodings))
        print("Known encodings:", len(KNOWN_FACE_ENCODINGS))

        if len(KNOWN_FACE_ENCODINGS) == 0:
            print("[ERRO] Nenhum rosto carregado na base de dados!")

        for encoding in face_encodings:

            if len(KNOWN_FACE_ENCODINGS) == 0:
                continue

            # 🔥 calcula distâncias primeiro (mais fiável)
            face_distances = face_recognition.face_distance(KNOWN_FACE_ENCODINGS, encoding)

            best_match_index = np.argmin(face_distances)

            # 🔥 tolerância (podes ajustar 0.5–0.6)
            if face_distances[best_match_index] < 0.5:
                name = KNOWN_FACE_NAMES[best_match_index]
            else:
                name = "Desconhecido"

        global current_detected_person
        current_detected_person = name

        return JsonResponse({
            "nome": name,
            "detectado": name != "Desconhecido"
        })

    except Exception as e:
        print("[ERRO gen_frames]:", str(e))
        return JsonResponse({"error": str(e)}, status=500)

def get_detected_person(request):
    """
    Endpoint para obter a pessoa atualmente detetada na cÃ¢mara.
    Retorna JSON com o nome da pessoa detetada ou None.
    """
    global current_detected_person
    return JsonResponse({
        'nome': current_detected_person,
        'detectado': current_detected_person is not None
    })

def camera_page(request):
    from django.shortcuts import render
    return render(request, "presencas/camera.html")

@require_http_methods(["POST"])
def registar_presenca(request):
    """
    Endpoint para registar uma presenÃ§a (entrada ou saÃ­da).
    Esperado JSON: {"nome": "Nome do Utilizador", "tipo": "entrada" ou "saida"}
    """
    try:
        data = json.loads(request.body)
        nome = data.get('nome')
        tipo = data.get('tipo', 'entrada')
        
        if not nome:
            return JsonResponse({'sucesso': False, 'erro': 'Nome nÃ£o fornecido'}, status=400)
        
        if tipo not in ['entrada', 'saida']:
            return JsonResponse({'sucesso': False, 'erro': 'Tipo invÃ¡lido'}, status=400)
        
        try:
            utilizador = FichaUtilizador.objects.get(nome=nome)
            presenca = Presenca(user=utilizador, tipo=tipo)
            presenca.save()
            data_hora_local = timezone.localtime(presenca.data_hora)
            return JsonResponse({
                'sucesso': True,
                'mensagem': f'PresenÃ§a registada: {nome} - {tipo.capitalize()}',
                'data_hora': data_hora_local.strftime('%d/%m/%Y %H:%M:%S')
            })
        except FichaUtilizador.DoesNotExist:
            return JsonResponse({'sucesso': False, 'erro': f'Utilizador {nome} nÃ£o encontrado'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'sucesso': False, 'erro': 'JSON invÃ¡lido'}, status=400)
    except Exception as e:
        return JsonResponse({'sucesso': False, 'erro': str(e)}, status=500)

@admin_required
def administracao(request):
    return render(request, "presencas/administracao.html", {"username": request.session.get("username")})

@admin_required
def lista_utilizadores(request):
    utilizadores = FichaUtilizador.objects.all().order_by('nome')
    
    # Aplicar filtro de pesquisa por nome
    pesquisa = request.GET.get('pesquisa', '')
    if pesquisa:
        utilizadores = utilizadores.filter(nome__icontains=pesquisa)
    
    return render(request, "presencas/lista_utilizadores.html", {
        "utilizadores": utilizadores,
        "pesquisa": pesquisa
    })


@admin_required
def adicionar_utilizador(request):
    error = None
    if request.method == "POST":
        username = request.POST.get("username")
        nome = request.POST.get("nome")
        email = request.POST.get("email")
        password = request.POST.get("password")
        administrador = request.POST.get("administrador") == "on"
        imagem = request.FILES.get("imagem")

        if not username or not nome or not password or not imagem:
            error = "Por favor, preencha todos os campos obrigatÃ³rios e escolha uma imagem."
        else:
            try:
                novo = FichaUtilizador(username=username, nome=nome, email=email, administrador=administrador, imagem=imagem)
                novo.set_password(password)
                return redirect("lista_utilizadores")
            except IntegrityError:
                error = "JÃ¡ existe um utilizador com esse username."

    return render(request, "presencas/adicionar_utilizador.html", {"error": error})


@admin_required
def editar_utilizador(request, user_id):
    utilizador = get_object_or_404(FichaUtilizador, id=user_id)

    error = None
    if request.method == "POST":
        utilizador.username = request.POST.get("username", utilizador.username)
        utilizador.nome = request.POST.get("nome", utilizador.nome)
        utilizador.email = request.POST.get("email", utilizador.email)

        password = request.POST.get("password")
        if password:
            utilizador.set_password(password)

        if "imagem" in request.FILES:
            utilizador.imagem = request.FILES.get("imagem")

        utilizador.administrador = request.POST.get("administrador") == "on"

        try:
            utilizador.save()
            return redirect("lista_utilizadores")
        except IntegrityError:
            error = "JÃ¡ existe um utilizador com esse username."

    return render(request, "presencas/editar_utilizador.html", {"utilizador": utilizador, "error": error})


@admin_required
def eliminar_utilizador(request, user_id):
    utilizador = get_object_or_404(FichaUtilizador, id=user_id)

    if request.method == "POST":
        utilizador.delete()
        return redirect("lista_utilizadores")

    return render(request, "presencas/eliminar_utilizador.html", {"utilizador": utilizador})
