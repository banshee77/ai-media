import streamlit as st
import qdrant_client
from langchain_community.vectorstores import Qdrant
from langchain.chains import RetrievalQA
from  langchain_community.embeddings import OllamaEmbeddings
from langchain_community.llms import Ollama

from transcribers.video_transcriber import Video2AudioConverter
from transcribers.audio_transcriber import AudioTranscription

from pytubefix import YouTube

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

import os

@st.cache_resource(show_spinner=False)
def initialize():
    embeddings = OllamaEmbeddings(base_url="http://localhost:11434", model='nomic-embed-text') 

    client_qdrant = qdrant_client.QdrantClient( "http://localhost:6333", prefer_grpc=True)
    vector_store_qdrant = Qdrant(
        client=client_qdrant, 
        collection_name="media_collection", 
        embeddings=embeddings,
    )
    
    retriever = vector_store_qdrant.as_retriever()

    if not os.path.exists("media"):
        os.makedirs("media")

    if not os.path.exists("transcriptions"):
        os.makedirs("transcriptions")
        
    return RetrievalQA.from_chain_type(llm=Ollama(model="llama3") , chain_type="stuff", retriever=retriever)

retrival_qa = initialize()

# query = "What makes the internet so addictive lately?"

st.set_page_config(
    page_title='Provide youtube link',
    page_icon='⚡',
    layout='wide',
    initial_sidebar_state='auto',
)

st.session_state["config"] = {}

@st.cache_resource
def video_transcription(config):
    # print(config)
    youtube_url = config.get("youtube_url",None)
    youtube = YouTube(youtube_url)
    video_title = youtube.title

    audio_path = './media/' + video_title.replace(' ', '_').lower() + '.mp3'
    transcription_path = audio_path.replace('./media/', './transcriptions/') + "_transcript.txt"
    
    if os.path.exists(audio_path):
        os.remove(audio_path)
    if os.path.exists(transcription_path):
        os.remove(transcription_path)
    
    # print(youtube_url)
    # print(output_path)
    Video2AudioConverter().download_youtube_audio(youtube_url, audio_path)

    AudioTranscription().transcribe(audio_file_dir='./media', is_log_enabled=False)
    return youtube.title, transcription_path

@st.cache_resource
def load_to_qdrant(transcription_path):
    # loader = DirectoryLoader('./transcriptions', glob="**/*.txt", show_progress=True)
    loader = TextLoader(transcription_path, encoding='utf-8')
    documents = loader.load_and_split(text_splitter=RecursiveCharacterTextSplitter())
    doc_sources = [document.metadata['source'] for document in documents]
    print(doc_sources)

    embeddings = OllamaEmbeddings(base_url="http://localhost:11434", model='nomic-embed-text') 

    url = "http://localhost:6333"
    Qdrant.from_documents(
        documents=documents,
        embedding=embeddings,
        url=url,
        prefer_grpc=True,
        collection_name="media_collection",
        force_recreate=True,
    )
    
with st.sidebar.form(key ='Form1'):
    st.markdown('## Provide Youtube link')
    youtube_url = st.text_input("URL", "https://www.youtube.com/watch?v=gWH2uhWgTvM")
    # https://www.youtube.com/watch?v=pLPJoFvq4_M
    # Please summarize "LangGraph Studio: The first agent IDE" video.    

    submitted1 = st.form_submit_button(label='Transcribe video')

    if submitted1 and youtube_url:
        st.session_state["config"] = {
            "youtube_url": youtube_url
        }
        config = st.session_state["config"]        
        youtube_title, transcription_path = video_transcription(st.session_state["config"])
        st.write(f"Youtube '{youtube_title}' video transcription completed successfully !")
        load_to_qdrant(transcription_path)
        st.write(f"Transcription successfully uploded to qdrant !")

st.title("Ask questions to uploaded video.")
if "messages" not in st.session_state.keys(): 
    st.session_state.messages = [
        {"role": "assistant", "content": "Ask me a question !"}
    ]

if prompt := st.chat_input("Your question"): 
    st.session_state.messages.append({"role": "user", "content": prompt})

for message in st.session_state.messages: 
    with st.chat_message(message["role"]):
        st.write(message["content"])
        
if st.session_state.messages[-1]["role"] != "assistant":
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = retrival_qa.invoke(prompt)
            st.write(response["result"])
            # print('\n----\n')
            # print(response["result"].strip())
            message = {"role": "assistant", "content": response["result"]}
            st.session_state.messages.append(message) 