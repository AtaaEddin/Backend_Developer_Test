from fastapi import FastAPI, Depends, HTTPException, Request, Body
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, validator
from cachetools import cached, TTLCache
from typing import List

app = FastAPI()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='login')

class User(BaseModel):
    email: str
    password: str

    @validator('email')
    def validate_email(cls, v):
        if '@' not in v:
            raise ValueError('Invalid email')
        return v.title

class Post(BaseModel):
    text: str
    user_id: int

    @validator('text')
    def validate_text(cls, v):
        if len(v) > 1048576:  # 1 MB
            raise ValueError('Payload too large')
        return v

class UserDB(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    password = Column(String)

class PostDB(Base):
    __tablename__ = 'posts'
    id = Column(Integer, primary_key=True)
    text = Column(String)
    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship('UserDB', backref='posts')

def get_db():
    db = Session(bind=engine)
    try:
        yield db
    finally:
        db.close()

def get_current_user(token: str = Depends(oauth2_scheme)):
    # implement token verification and user retrieval
    pass

@app.post('/signup')
async def signup(user: User, db: Session = Depends(get_db)):
    try:
        user_db = UserDB(email=user.email, password=user.password)
        db.add(user_db)
        db.commit()
        return {'token': generate_token(user.email)}
    except IntegrityError:
        return JSONResponse(status_code=400, content={'error': 'Email already exists'})

@app.post('/login')
async def login(user: User, db: Session = Depends(get_db)):
    user_db = db.query(UserDB).filter_by(email=user.email, password=user.password).first()
    if user_db:
        return {'token': generate_token(user.email)}
    return JSONResponse(status_code=401, content={'error': 'Invalid credentials'})

cache = TTLCache(maxsize=100, ttl=300)  # 5 minutes

@app.post('/AddPost')
async def add_post(post: Post, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = get_current_user(token)
    if not user:
        return JSONResponse(status_code=401, content={'error': 'Invalid token'})
    post_db = PostDB(text=post.text, user_id=user.id)
    db.add(post_db)
    db.commit()
    return {'post_id': post_db.id}

@app.get('/GetPosts')
@cached(cache, key='GetPosts:{user_id}')
async def get_posts(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = get_current_user(token)
    if not user:
        return JSONResponse(status_code=401, content={'error': 'Invalid token'})
    posts = db.query(PostDB).filter_by(user_id=user.id).all()
    return {'posts': [post.text for post in posts]}

@app.delete('/DeletePost/{post_id}')
async def delete_post(post_id: int, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = get_current_user(token)
    if not user:
        return JSONResponse(status_code=401, content={'error': 'Invalid token'})
    post = db.query(PostDB).filter_by(id=post_id, user_id=user.id).first()
    if post:
        db.delete(post)
        db.commit()
        return {'message': 'Post deleted'}
    return JSONResponse(status_code=404, content={'error': 'Post not found'})