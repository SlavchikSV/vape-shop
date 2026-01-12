web: gunicorn app:app
release: git pull && python -c "
import subprocess
import os

# Настраиваем Git
if not os.path.exists('.git'):
    subprocess.run(['git', 'init'])
    
subprocess.run(['git', 'config', 'user.email', 'slavaveselov2006@gmail.com'])
subprocess.run(['git', 'config', 'user.name', 'SlavchikSV'])

print('✅ Git настроен')
"
