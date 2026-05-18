import { Bold, Code, Image, Italic, Sigma } from "lucide-react";
import { type ChangeEvent, type ClipboardEvent, useRef, useState } from "react";

import { Button, StatusMessage, TextareaField } from "../../components/ui";
import { cn } from "../../lib/utils";
import { CardContentRenderer } from "./card-content-renderer";

interface CardContentEditorProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  uploadImage?: (file: File) => Promise<{ markdown: string }>;
  rows?: number;
  placeholder?: string;
}

export function CardContentEditor({
  label,
  value,
  onChange,
  uploadImage,
  rows = 5,
  placeholder,
}: CardContentEditorProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [mode, setMode] = useState<"write" | "preview">("write");
  const [uploading, setUploading] = useState(false);
  const [errorText, setErrorText] = useState("");

  function insertText(text: string) {
    const textarea = textareaRef.current;
    if (!textarea || document.activeElement !== textarea) {
      onChange(value ? `${value}${text.startsWith(" ") ? "" : " "}${text}` : text);
      return;
    }

    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const prefix = value.slice(0, start);
    const suffix = value.slice(end);
    onChange(`${prefix}${text}${suffix}`);
    window.requestAnimationFrame(() => {
      textarea.focus();
      textarea.setSelectionRange(start + text.length, start + text.length);
    });
  }

  async function insertImage(file: File) {
    if (!uploadImage) {
      setErrorText("Image upload is not available.");
      return;
    }

    setUploading(true);
    setErrorText("");
    try {
      const result = await uploadImage(file);
      const separator = value.trim() ? "\n\n" : "";
      onChange(`${value}${separator}${result.markdown}`);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : "Image upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) {
      await insertImage(file);
    }
  }

  function handlePaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const imageItem = Array.from(event.clipboardData.items).find(
      (item) => item.kind === "file" && item.type.startsWith("image/"),
    );
    const file = imageItem?.getAsFile();
    if (!file) {
      return;
    }
    event.preventDefault();
    void insertImage(file);
  }

  return (
    <div className="card-content-editor">
      <span className="card-content-editor-label">{label}</span>
      <div className="card-content-editor-toolbar" role="toolbar" aria-label="Formatting tools">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="card-content-editor-tool"
          aria-label="Insert bold"
          onClick={() => insertText("**bold**")}
        >
          <Bold size={16} aria-hidden="true" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="card-content-editor-tool"
          aria-label="Insert italic"
          onClick={() => insertText("*italic*")}
        >
          <Italic size={16} aria-hidden="true" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="card-content-editor-tool"
          aria-label="Insert inline code"
          onClick={() => insertText("`code`")}
        >
          <Code size={16} aria-hidden="true" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="card-content-editor-tool"
          aria-label="Insert inline math"
          onClick={() => insertText(value.trim() ? " $x$" : "$x$")}
        >
          <Sigma size={16} aria-hidden="true" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="card-content-editor-tool"
          aria-label="Insert block math"
          onClick={() => insertText("$$\n\n$$")}
        >
          <Sigma size={16} aria-hidden="true" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="card-content-editor-tool"
          aria-label="Insert image"
          onClick={() => fileInputRef.current?.click()}
          disabled={!uploadImage || uploading}
        >
          <Image size={16} aria-hidden="true" />
        </Button>
        <button
          type="button"
          className={cn("card-content-editor-tab", mode === "write" && "is-active")}
          onClick={() => setMode("write")}
        >
          Write
        </button>
        <button
          type="button"
          className={cn("card-content-editor-tab", mode === "preview" && "is-active")}
          onClick={() => setMode("preview")}
        >
          Preview
        </button>
      </div>
      <input
        ref={fileInputRef}
        className="sr-only"
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif"
        onChange={(event) => void handleFileChange(event)}
      />
      {mode === "write" ? (
        <TextareaField
          ref={textareaRef}
          aria-label={label}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onPaste={handlePaste}
          rows={rows}
          placeholder={placeholder}
        />
      ) : (
        <div className="card-content-editor-preview">
          <CardContentRenderer content={value || " "} variant="preview" />
        </div>
      )}
      {uploading ? <StatusMessage tone="info">Uploading image...</StatusMessage> : null}
      {errorText ? <StatusMessage tone="error">{errorText}</StatusMessage> : null}
    </div>
  );
}
