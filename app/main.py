from fastapi import FastAPI

from app import settings

app = FastAPI()


@app.on_event("startup")
async def startup_event():
    pass


@app.on_event("shutdown")
async def shutdown_event():
    pass


from app.routers import users

app.include_router(users.router)
