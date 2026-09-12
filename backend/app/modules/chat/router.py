"""Chat/Conversation Module HTTP surface (plan Section E). Maps to the
existing Flutter ChatRepository contract (loadMessages/saveUserMessage/
createAssistantReply) so ApiChatRepository (Phase 1, owner: Aranj) can be
built directly against this without any client-side redesign."""

from fastapi import APIRouter, Depends

from app.modules.auth.schemas import CurrentIdentity
from app.modules.auth.service import get_current_identity
from app.modules.chat import service
from app.modules.chat.schemas import ConversationOut, CreateMessageRequest, MessageOut

router = APIRouter()


@router.post("/conversations", response_model=ConversationOut)
def create_conversation(identity: CurrentIdentity = Depends(get_current_identity)) -> ConversationOut:
    conv = service.create_conversation(tenant_id=identity.tenant_id, user_id=identity.user_id)
    return ConversationOut(**conv.__dict__)


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(identity: CurrentIdentity = Depends(get_current_identity)) -> list[ConversationOut]:
    convs = service.list_conversations(tenant_id=identity.tenant_id, user_id=identity.user_id)
    return [ConversationOut(**c.__dict__) for c in convs]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(
    conversation_id: str, identity: CurrentIdentity = Depends(get_current_identity)
) -> list[MessageOut]:
    msgs = service.list_messages(tenant_id=identity.tenant_id, conversation_id=conversation_id)
    return [MessageOut(**m.__dict__) for m in msgs]


@router.post("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def post_message(
    conversation_id: str,
    body: CreateMessageRequest,
    identity: CurrentIdentity = Depends(get_current_identity),
) -> list[MessageOut]:
    user_msg, assistant_msg = await service.post_user_message(
        tenant_id=identity.tenant_id, conversation_id=conversation_id, content=body.content
    )
    return [MessageOut(**user_msg.__dict__), MessageOut(**assistant_msg.__dict__)]
