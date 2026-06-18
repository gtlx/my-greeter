use serde::{Deserialize, Serialize};
use std::io::{Read, Write};
use std::os::unix::net::UnixStream;

#[derive(Serialize)]
#[serde(tag = "type")]
pub enum Request {
    #[serde(rename = "create_session")]
    CreateSession { username: String },
    #[serde(rename = "post_auth_message_response")]
    PostAuthMessageResponse {
        #[serde(skip_serializing_if = "Option::is_none")]
        response: Option<String>,
    },
    #[serde(rename = "start_session")]
    StartSession {
        cmd: Vec<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        env: Option<Vec<String>>,
    },
    #[serde(rename = "cancel_session")]
    CancelSession,
}

#[derive(Deserialize, Debug)]
#[serde(tag = "type")]
pub enum Response {
    #[serde(rename = "success")]
    Success,
    #[serde(rename = "error")]
    Error {
        error_type: String,
        description: Option<String>,
    },
    #[serde(rename = "auth_message")]
    AuthMessage {
        auth_message_type: String,
        #[serde(default)]
        auth_message: String,
    },
}

pub struct GreetdClient {
    stream: UnixStream,
}

impl GreetdClient {
    pub fn connect() -> Result<Self, String> {
        let sock_path = std::env::var("GREETD_SOCK")
            .map_err(|_| "GREETD_SOCK not set".to_string())?;
        let stream = UnixStream::connect(&sock_path)
            .map_err(|e| format!("connect failed: {}", e))?;
        Ok(Self { stream })
    }

    fn send(&mut self, req: &Request) -> Result<(), String> {
        let payload = serde_json::to_string(req)
            .map_err(|e| format!("serialize: {}", e))?;
        let len = payload.len() as u32;
        let header = len.to_ne_bytes();
        self.stream.write_all(&header)
            .map_err(|e| format!("write header: {}", e))?;
        self.stream.write_all(payload.as_bytes())
            .map_err(|e| format!("write payload: {}", e))?;
        Ok(())
    }

    fn recv(&mut self) -> Result<Response, String> {
        let mut header = [0u8; 4];
        self.stream.read_exact(&mut header)
            .map_err(|e| format!("read header: {}", e))?;
        let len = u32::from_ne_bytes(header) as usize;
        let mut buf = vec![0u8; len];
        let mut read = 0;
        while read < len {
            let n = self.stream.read(&mut buf[read..])
                .map_err(|e| format!("read payload: {}", e))?;
            if n == 0 {
                return Err("connection closed".to_string());
            }
            read += n;
        }
        serde_json::from_slice(&buf)
            .map_err(|e| format!("parse: {} (raw: {})", e, String::from_utf8_lossy(&buf)))
    }

    pub fn create_session(&mut self, username: &str) -> Result<Response, String> {
        self.send(&Request::CreateSession { username: username.to_string() })?;
        self.recv()
    }

    pub fn auth_response(&mut self, response: Option<&str>) -> Result<Response, String> {
        self.send(&Request::PostAuthMessageResponse {
            response: response.map(|s| s.to_string()),
        })?;
        self.recv()
    }

    pub fn start_session(&mut self, cmd: &[String], env: &[String]) -> Result<Response, String> {
        self.send(&Request::StartSession {
            cmd: cmd.to_vec(),
            env: Some(env.to_vec()),
        })?;
        self.recv()
    }

    pub fn cancel(&mut self) -> Result<Response, String> {
        self.send(&Request::CancelSession)?;
        self.recv()
    }
}
