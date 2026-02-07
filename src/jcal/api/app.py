from fastapi import FastAPI
from jcal.api.public import router as public_router

app = FastAPI(title="jcal public api")
app.include_router(public_router)