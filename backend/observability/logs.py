"""
Queryable structured logging with filtering and search.

Provides:
- In-memory log storage
- Filtering by trace, agent, level, timestamp
- Full-text search
- Log persistence and replay
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID


class LogLevel(str, Enum):
    """Log severity levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class LogEntry:
    """Single structured log entry."""
    
    timestamp: datetime
    level: LogLevel
    logger: str  # e.g., "agents.search_agent"
    message: str
    
    trace_id: UUID
    conversation_id: UUID
    agent_id: Optional[str] = None
    
    # Structured fields
    fields: Dict[str, Any] = field(default_factory=dict)
    
    # Stack trace for errors
    exception: Optional[str] = None
    
    # Correlation
    parent_trace_id: Optional[UUID] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "logger": self.logger,
            "message": self.message,
            "trace_id": str(self.trace_id),
            "conversation_id": str(self.conversation_id),
            "agent_id": self.agent_id,
            "fields": self.fields,
            "exception": self.exception,
            "parent_trace_id": str(self.parent_trace_id) if self.parent_trace_id else None,
        }


class LogRepository:
    """In-memory queryable log repository."""
    
    def __init__(self, max_entries: int = 100000):
        self.entries: List[LogEntry] = []
        self.max_entries = max_entries
        
        # Indexes for fast lookups
        self.by_trace: Dict[UUID, List[LogEntry]] = {}
        self.by_agent: Dict[str, List[LogEntry]] = {}
        self.by_conversation: Dict[UUID, List[LogEntry]] = {}
        self.by_level: Dict[LogLevel, List[LogEntry]] = {}
    
    def add(self, entry: LogEntry) -> None:
        """Add a log entry."""
        self.entries.append(entry)
        
        # Update indexes
        if entry.trace_id not in self.by_trace:
            self.by_trace[entry.trace_id] = []
        self.by_trace[entry.trace_id].append(entry)
        
        if entry.agent_id:
            if entry.agent_id not in self.by_agent:
                self.by_agent[entry.agent_id] = []
            self.by_agent[entry.agent_id].append(entry)
        
        if entry.conversation_id not in self.by_conversation:
            self.by_conversation[entry.conversation_id] = []
        self.by_conversation[entry.conversation_id].append(entry)
        
        if entry.level not in self.by_level:
            self.by_level[entry.level] = []
        self.by_level[entry.level].append(entry)
        
        # Enforce max size
        if len(self.entries) > self.max_entries:
            # Remove oldest 10%
            to_remove = int(self.max_entries * 0.1)
            removed = self.entries[:to_remove]
            self.entries = self.entries[to_remove:]
            
            # Update indexes
            for entry in removed:
                if entry.trace_id in self.by_trace:
                    self.by_trace[entry.trace_id].remove(entry)
                if entry.agent_id and entry.agent_id in self.by_agent:
                    self.by_agent[entry.agent_id].remove(entry)
    
    def get_by_trace(self, trace_id: UUID) -> List[LogEntry]:
        """Get all logs for a trace."""
        return self.by_trace.get(trace_id, [])
    
    def get_by_agent(self, agent_id: str) -> List[LogEntry]:
        """Get all logs for an agent."""
        return self.by_agent.get(agent_id, [])
    
    def get_by_conversation(self, conversation_id: UUID) -> List[LogEntry]:
        """Get all logs for a conversation."""
        return self.by_conversation.get(conversation_id, [])
    
    def get_by_level(self, level: LogLevel) -> List[LogEntry]:
        """Get all logs at a specific level."""
        return self.by_level.get(level, [])
    
    def get_errors_and_warnings(self) -> List[LogEntry]:
        """Get all ERROR and WARNING level logs."""
        return (
            self.by_level.get(LogLevel.ERROR, []) +
            self.by_level.get(LogLevel.WARNING, []) +
            self.by_level.get(LogLevel.CRITICAL, [])
        )
    
    def search(
        self,
        query: str,
        trace_id: Optional[UUID] = None,
        agent_id: Optional[str] = None,
        level: Optional[LogLevel] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[LogEntry]:
        """Search logs with filters."""
        
        # Start with full list or filtered by trace
        if trace_id:
            results = self.get_by_trace(trace_id)
        elif agent_id:
            results = self.get_by_agent(agent_id)
        else:
            results = self.entries[:]
        
        # Apply filters
        if level:
            results = [e for e in results if e.level == level]
        
        if start_time:
            results = [e for e in results if e.timestamp >= start_time]
        
        if end_time:
            results = [e for e in results if e.timestamp <= end_time]
        
        # Full-text search in message and fields
        if query:
            query_lower = query.lower()
            results = [
                e for e in results
                if (
                    query_lower in e.message.lower() or
                    any(query_lower in str(v).lower() for v in e.fields.values())
                )
            ]
        
        return results[:limit]
    
    def get_recent(self, limit: int = 100) -> List[LogEntry]:
        """Get most recent log entries."""
        return self.entries[-limit:]
    
    def get_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000,
    ) -> List[LogEntry]:
        """Get logs within a time range."""
        return [
            e for e in self.entries
            if start_time <= e.timestamp <= end_time
        ][:limit]
    
    def get_last_n_minutes(self, minutes: int = 5) -> List[LogEntry]:
        """Get logs from last N minutes."""
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        return self.get_by_time_range(cutoff, datetime.utcnow())
    
    def get_stats(self) -> Dict[str, Any]:
        """Get repository statistics."""
        return {
            "total_entries": len(self.entries),
            "max_entries": self.max_entries,
            "traces": len(self.by_trace),
            "agents": len(self.by_agent),
            "conversations": len(self.by_conversation),
            "by_level": {level.value: len(entries) for level, entries in self.by_level.items()},
        }


class LoggerFactory:
    """Factory for creating configured loggers."""
    
    def __init__(self, repository: LogRepository):
        self.repository = repository
    
    def get_logger(self, name: str) -> StructuredLogger:
        """Get a logger instance."""
        return StructuredLogger(name, self.repository)


class StructuredLogger:
    """Structured logger that emits to repository."""
    
    def __init__(self, name: str, repository: LogRepository):
        self.name = name
        self.repository = repository
    
    def log(
        self,
        level: LogLevel,
        message: str,
        trace_id: UUID,
        conversation_id: UUID,
        agent_id: Optional[str] = None,
        **fields: Any
    ) -> None:
        """Emit a log entry."""
        entry = LogEntry(
            timestamp=datetime.utcnow(),
            level=level,
            logger=self.name,
            message=message,
            trace_id=trace_id,
            conversation_id=conversation_id,
            agent_id=agent_id,
            fields=fields,
        )
        self.repository.add(entry)
    
    def debug(
        self,
        message: str,
        trace_id: UUID,
        conversation_id: UUID,
        **fields: Any
    ) -> None:
        """Emit debug log."""
        self.log(LogLevel.DEBUG, message, trace_id, conversation_id, **fields)
    
    def info(
        self,
        message: str,
        trace_id: UUID,
        conversation_id: UUID,
        **fields: Any
    ) -> None:
        """Emit info log."""
        self.log(LogLevel.INFO, message, trace_id, conversation_id, **fields)
    
    def warning(
        self,
        message: str,
        trace_id: UUID,
        conversation_id: UUID,
        **fields: Any
    ) -> None:
        """Emit warning log."""
        self.log(LogLevel.WARNING, message, trace_id, conversation_id, **fields)
    
    def error(
        self,
        message: str,
        trace_id: UUID,
        conversation_id: UUID,
        **fields: Any
    ) -> None:
        """Emit error log."""
        self.log(LogLevel.ERROR, message, trace_id, conversation_id, **fields)
    
    def critical(
        self,
        message: str,
        trace_id: UUID,
        conversation_id: UUID,
        **fields: Any
    ) -> None:
        """Emit critical log."""
        self.log(LogLevel.CRITICAL, message, trace_id, conversation_id, **fields)


# Global repository
_log_repository: Optional[LogRepository] = None


def get_log_repository() -> LogRepository:
    """Get or create global log repository."""
    global _log_repository
    if _log_repository is None:
        _log_repository = LogRepository()
    return _log_repository


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger."""
    repo = get_log_repository()
    return StructuredLogger(name, repo)
