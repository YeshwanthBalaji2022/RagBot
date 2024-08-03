import os
import streamlit as st
from pinecone import Pinecone
from langchain.document_loaders import PyPDFDirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings.cohere import CohereEmbeddings
from langchain.llms import Cohere
from langchain.chains.question_answering import load_qa_chain
import cohere
from dotenv import load_dotenv

load_dotenv()

def read_doc(directory):
    file_loader = PyPDFDirectoryLoader(directory)
    docs = file_loader.load()
    return docs

def chunkIt(docs, chunk_size=800, chunk_overlap=50):
    ts = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    doc = ts.split_documents(docs)
    return doc

def retrieve_query(query, index, embedding, k=2):
    query_embedding = embedding.embed_documents([query])[0]
    result = index.query(
        top_k=k,
        include_values=True,
        include_metadata=True,
        vector=query_embedding
    )
    documents = result['matches']
    return documents

def retrieve_answers(query, index, embedding, chain):
    docsearch = retrieve_query(query, index, embedding)
    response = chain.run(input_documents=docsearch, question=query)
    return response

st.title("RAG Chatbot(Without Memory)")

with st.sidebar:
    st.subheader("Configuration")
    cohere_api_key = st.text_input("Enter Your Cohere API Key", type="password")
    pinecone_api_key = st.text_input("Enter Your Pinecone API Key", type="password")
    pinecone_index_name = st.text_input("Enter Pinecone Index Name")

    if cohere_api_key and pinecone_api_key and pinecone_index_name:
        os.environ['COHERE_API_KEY'] = cohere_api_key
        os.environ['PINECONE_API_KEY'] = pinecone_api_key

        pc= Pinecone(api_key=pinecone_api_key)
        index = pc.Index(pinecone_index_name)

        uploaded_files = st.file_uploader("Upload PDF files", accept_multiple_files=True, type="pdf")

        if uploaded_files:
            save_dir = "./uploaded_docs/"
            os.makedirs(save_dir, exist_ok=True)
            for file in uploaded_files:
                with open(os.path.join(save_dir, file.name), "wb") as f:
                    f.write(file.getbuffer())

            docs = read_doc(save_dir)
            documents = chunkIt(docs=docs)
            documentss = [str(doc) for doc in documents]

            embedding = CohereEmbeddings(cohere_api_key=os.environ["COHERE_API_KEY"], user_agent="user")
            embeddings = embedding.embed_documents(texts=documentss)

            vectors = []
            for i, doc in enumerate(documents):
                vector = embeddings[i]
                metadata = {"text": doc.page_content}
                vectors.append((str(i), vector, metadata))

            try:
                index.upsert(vectors=vectors)
                st.sidebar.success("Documents have been processed and indexed.")
            except Exception as e:
                st.sidebar.error(f"Error during upsert: {e}")

            cohere_client = cohere.Client(api_key=os.environ["COHERE_API_KEY"])
            llm = Cohere(client=cohere_client)
            chain = load_qa_chain(llm, chain_type="stuff")
            st.session_state.qa_chain = chain
            st.session_state.index = index
            st.session_state.embedding = embedding

if 'messages' not in st.session_state:
    st.session_state.messages = []

if 'qa_chain' not in st.session_state:
    st.session_state.qa_chain = None

if 'index' not in st.session_state:
    st.session_state.index = None

if 'embedding' not in st.session_state:
    st.session_state.embedding = None

for message in st.session_state.messages:
    st.chat_message(message['role']).markdown(message['content'])

query = st.chat_input("Ask your question")

if query and st.session_state.qa_chain and st.session_state.index and st.session_state.embedding:
    st.chat_message('user').markdown(query)
    
    response = retrieve_answers(query, st.session_state.index, st.session_state.embedding, st.session_state.qa_chain)
    
    st.chat_message("assistant").markdown(response)
    
    st.session_state.messages.append({'role': 'user', 'content': query})
    st.session_state.messages.append({'role': 'assistant', 'content': response})
else:
    st.warning("Please configure the API keys and upload documents.")
