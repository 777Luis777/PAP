from django.db import models
from django.contrib.auth.hashers import make_password, check_password

# --- UTILIZADOR ---
class FichaUtilizador(models.Model):
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=256)  # hash da password
    nome = models.CharField(max_length=100)
    imagem = models.ImageField(upload_to="img/")
    administrador = models.BooleanField(default=False)

    def set_password(self, raw_password):
        self.password = make_password(raw_password)
        self.save()

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def __str__(self):
        return self.username


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
