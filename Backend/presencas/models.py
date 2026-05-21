from django.db import models
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
from datetime import timedelta
import secrets

# --- UTILIZADOR ---
class FichaUtilizador(models.Model):
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=256)  # hash da password
    nome = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    imagem = models.ImageField(upload_to="img/")
    administrador = models.BooleanField(default=False)

    def set_password(self, raw_password):
        self.password = make_password(raw_password)
        self.save()

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def __str__(self):
        return self.username


# --- RECUPERAÇÃO DE PALAVRA-PASSE ---
class PasswordResetToken(models.Model):
    user = models.ForeignKey(FichaUtilizador, on_delete=models.CASCADE)
    token = models.CharField(max_length=100, unique=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    expirado_em = models.DateTimeField()

    def is_valid(self):
        return timezone.now() < self.expirado_em

    def __str__(self):
        return f"Token de {self.user.username} - Válido até {self.expirado_em}"

    @staticmethod
    def criar_token(user):
        """Cria um novo token de recuperação de palavra-passe"""
        # Remover tokens antigos
        PasswordResetToken.objects.filter(user=user).delete()
        
        # Criar novo token (válido por 1 hora)
        token = secrets.token_urlsafe(32)
        expirado_em = timezone.now() + timedelta(hours=1)
        
        return PasswordResetToken.objects.create(
            user=user,
            token=token,
            expirado_em=expirado_em
        )


# --- PRESENÇA ---
class Presenca(models.Model):
    TIPO_CHOICES = [
        ('entrada', 'Entrada'),
        ('saida', 'Saída'),
    ]
    
    user = models.ForeignKey(FichaUtilizador, on_delete=models.CASCADE)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='entrada')
    data_hora = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.nome} - {self.tipo} - {self.data_hora}"
