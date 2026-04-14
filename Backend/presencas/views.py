import sqlite3
import face_recognition
import numpy as np
import cv2
import io
import datetime
import os
from django.http import StreamingHttpResponse
from django.conf import settings
from django.db import IntegrityError
from PIL import Image
from functools import wraps
from django.shortcuts import render, redirect, get_object_or_404
from .models import FichaUtilizador

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
            return render(request, "presencas/login.html", {"error": "Username não existe"})

    return render(request, "presencas/login.html")

def logout(request):
    request.session.flush()
    return redirect("login")

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
    return render(request, "presencas/presencas.html", {"username": request.session.get('username')})

def load_known_faces():
    # use the Django ORM instead of a raw sqlite connection; this
    # keeps the code database‑agnostic and uses the configured DB path.
    registos = FichaUtilizador.objects.values_list("nome", "imagem")

    known_face_encodings = []
    known_face_names = []

    for nome, caminho_imagem in registos:
        # imagem field may already be a path-like object so cast to str
        caminho_completo = os.path.normpath(os.path.join(settings.MEDIA_ROOT, str(caminho_imagem)))
        if not os.path.exists(caminho_completo):
            print(f"[!] Imagem não encontrada: {caminho_completo}")
            continue

        imagem = Image.open(caminho_completo).convert("RGB")
        imagem_np = np.array(imagem, dtype=np.uint8)
        encodings = face_recognition.face_encodings(imagem_np)

        if encodings:
            known_face_encodings.append(encodings[0])
            known_face_names.append(nome)
        else:
            print(f"[!] Nenhum rosto encontrado na imagem de {nome}")

    return known_face_encodings, known_face_names

# Carregar rostos uma vez
KNOWN_FACE_ENCODINGS, KNOWN_FACE_NAMES = load_known_faces()


def gen_frames():
    video_capture = cv2.VideoCapture(0)
    if not video_capture.isOpened():
        print("[!] Erro ao abrir a câmara")
        return

    process_this_frame = True

    while True:
        ret, frame = video_capture.read()
        if not ret:
            break

        # Reduzir tamanho para acelerar detecção
        small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        face_locations = []
        face_names = []

        if process_this_frame:
            face_locations = face_recognition.face_locations(rgb_small_frame)
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

            for face_encoding in face_encodings:
                matches = face_recognition.compare_faces(KNOWN_FACE_ENCODINGS, face_encoding)
                name = "Desconhecido"

                if KNOWN_FACE_ENCODINGS:
                    face_distances = face_recognition.face_distance(KNOWN_FACE_ENCODINGS, face_encoding)
                    best_match_index = np.argmin(face_distances)
                    if matches[best_match_index]:
                        name = KNOWN_FACE_NAMES[best_match_index]

                face_names.append(name)

        process_this_frame = not process_this_frame

        # Desenhar caixas e nomes
        for (top, right, bottom, left), name in zip(face_locations, face_names):
            top *= 4
            right *= 4
            bottom *= 4
            left *= 4

            cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)
            cv2.rectangle(frame, (left, bottom - 35), (right, bottom), (0, 0, 255), cv2.FILLED)
            cv2.putText(frame, name, (left + 6, bottom - 6), cv2.FONT_HERSHEY_DUPLEX, 1.0, (255, 255, 255), 1)

        # Codifica frame em JPEG
        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

    video_capture.release()


def camera_feed(request):
    return StreamingHttpResponse(gen_frames(),
                                 content_type='multipart/x-mixed-replace; boundary=frame')


def camera_page(request):
    from django.shortcuts import render
    return render(request, "presencas/camera.html")

@admin_required
def administracao(request):
    return render(request, "presencas/administracao.html", {"username": request.session.get("username")})

@admin_required
def lista_utilizadores(request):
    utilizadores = FichaUtilizador.objects.all()
    return render(request, "presencas/lista_utilizadores.html", {"utilizadores": utilizadores})


@admin_required
def adicionar_utilizador(request):
    error = None
    if request.method == "POST":
        username = request.POST.get("username")
        nome = request.POST.get("nome")
        password = request.POST.get("password")
        administrador = request.POST.get("administrador") == "on"
        imagem = request.FILES.get("imagem")

        if not username or not nome or not password or not imagem:
            error = "Por favor, preencha todos os campos obrigatórios e escolha uma imagem."
        else:
            try:
                novo = FichaUtilizador(username=username, nome=nome, administrador=administrador, imagem=imagem)
                novo.set_password(password)
                return redirect("lista_utilizadores")
            except IntegrityError:
                error = "Já existe um utilizador com esse username."

    return render(request, "presencas/adicionar_utilizador.html", {"error": error})


@admin_required
def editar_utilizador(request, user_id):
    utilizador = get_object_or_404(FichaUtilizador, id=user_id)

    error = None
    if request.method == "POST":
        utilizador.username = request.POST.get("username", utilizador.username)
        utilizador.nome = request.POST.get("nome", utilizador.nome)

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
            error = "Já existe um utilizador com esse username."

    return render(request, "presencas/editar_utilizador.html", {"utilizador": utilizador, "error": error})


@admin_required
def eliminar_utilizador(request, user_id):
    utilizador = get_object_or_404(FichaUtilizador, id=user_id)

    if request.method == "POST":
        utilizador.delete()
        return redirect("lista_utilizadores")

    return render(request, "presencas/eliminar_utilizador.html", {"utilizador": utilizador})
