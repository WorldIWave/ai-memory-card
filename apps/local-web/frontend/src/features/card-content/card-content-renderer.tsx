import "katex/dist/katex.min.css";

import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { cn } from "../../lib/utils";

interface CardContentRendererProps {
  content: string;
  className?: string;
  variant?: "compact" | "review" | "preview";
}

export function CardContentRenderer({
  content,
  className,
  variant = "compact",
}: CardContentRendererProps) {
  return (
    <div className={cn("card-content-renderer", `card-content-${variant}`, className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          strong({ children }) {
            return <strong className="font-semibold">{children}</strong>;
          },
          a({ children, href }) {
            return (
              <a href={href} target="_blank" rel="noreferrer">
                {children}
              </a>
            );
          },
          p({ children }) {
            return <p className={variant === "review" ? className : undefined}>{children}</p>;
          },
          img({ alt, src }) {
            return <img alt={alt ?? ""} src={src ?? ""} loading="lazy" />;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
