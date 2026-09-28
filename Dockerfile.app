FROM mwm-base

# Set working directory (should match the base image's WORKDIR)
WORKDIR /app

# Copy the source code
COPY app app
COPY config.py config.py
COPY run.py run.py

# Copy Gunicorn configuration file
COPY gunicorn_config.py gunicorn_config.py

# Expose the port the application will run on
EXPOSE 8000

# Use Gunicorn to run the application
#CMD ["gunicorn", "-c", "gunicorn_config.py", "app:app"]

# Supervisor 설정 복사
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Supervisor를 ENTRYPOINT로 설정
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]