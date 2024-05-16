import sqlalchemy as db
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from constants import DbConstant

Base = declarative_base()


class Chat(Base):
    __tablename__ = 'chats'

    vk_user_id = db.Column(db.Integer, primary_key=True)
    vk_user = db.Column(db.String)
    tg_chat_id = db.Column(db.BigInteger)


class Message(Base):
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    vk_user_id = db.Column(db.BigInteger, db.ForeignKey('chats.vk_user_id'))
    tg_message_id = db.Column(db.Integer)
    vk_message_id = db.Column(db.Integer)


class Database:
    def __init__(self):
        engine_args = {
            'url': DbConstant.DB_URL.value,
        }
        if DbConstant.USE_POSTGRES.value:
            engine_args['echo'] = DbConstant.ECHO.value
        engine = db.create_engine(**engine_args)
        self.Session = sessionmaker(bind=engine)

        Base.metadata.create_all(engine)

    def add_chat(self, vk_user, vk_user_id, tg_chat_id):
        with self.Session() as session:
            chat = Chat(
                vk_user=vk_user,
                vk_user_id=vk_user_id,
                tg_chat_id=tg_chat_id,
            )
            session.add(chat)
            session.commit()

    def update_chat(self, vk_user_id, new_vk_user, tg_chat_id):
        with self.Session() as session:
            chat = session.query(Chat).filter_by(
                vk_user_id=vk_user_id,
            ).first()

            if chat:
                chat.vk_user = new_vk_user
                chat.tg_chat_id = tg_chat_id
                session.commit()

    def get_chat(self, vk_user_id=None, tg_chat_id=None):
        with self.Session() as session:
            if vk_user_id:
                return session.query(Chat).filter_by(
                    vk_user_id=vk_user_id
                ).first()
            elif tg_chat_id:
                return session.query(Chat).filter_by(
                    tg_chat_id=tg_chat_id
                ).first()

    def delete_chat(self, tg_chat_id):
        with self.Session() as session:
            chat = session.query(Chat).filter_by(
                tg_chat_id=tg_chat_id
            ).first()

            if chat:
                session.delete(chat)
                session.commit()

    def add_message(self, vk_user_id, tg_message_id, vk_message_id):
        with self.Session() as session:
            messages = session.query(Message).filter_by(
                vk_user_id=vk_user_id
            ).order_by(Message.id).all()

            if len(messages) >= 1000:
                oldest_message = messages[0]
                session.delete(oldest_message)
                session.commit()

            message = Message(
                vk_user_id=vk_user_id,
                tg_message_id=tg_message_id,
                vk_message_id=vk_message_id,
            )
            session.add(message)
            session.commit()

    def get_message(
            self,
            vk_user_id=None,
            tg_message_id=None,
            vk_message_id=None
    ):
        with self.Session() as session:
            if vk_user_id:
                return session.query(Message).filter_by(
                    vk_user_id=vk_user_id,
                    tg_message_id=tg_message_id,
                ).first()

            elif vk_message_id:
                return session.query(Message).filter_by(
                    vk_message_id=vk_message_id,
                ).first()
