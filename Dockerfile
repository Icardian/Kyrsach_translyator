FROM python:3.12-slim AS test
WORKDIR /app
COPY sql2py ./sql2py
COPY tests ./tests
COPY examples ./examples
COPY tools ./tools
RUN python -m unittest discover -s tests -v

FROM python:3.12-slim
COPY --from=test /app/sql2py /opt/sql2py/sql2py
ENV PYTHONPATH=/opt/sql2py
WORKDIR /work
ENTRYPOINT ["python", "-m", "sql2py"]
CMD ["--help"]
