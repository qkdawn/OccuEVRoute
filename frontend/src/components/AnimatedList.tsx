import { motion, useInView } from "motion/react";
import type { ReactNode } from "react";
import { Children, useRef } from "react";
import "./AnimatedList.css";

interface AnimatedItemProps {
  children: ReactNode;
  delay: number;
  index: number;
}

function AnimatedItem({ children, delay, index }: AnimatedItemProps) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { amount: 0.3, once: true });
  const sheenDelay = Math.min(index, 4) * 70;

  return (
    <motion.div
      ref={ref}
      className="animated-list-item"
      style={{ "--sheen-delay": `${sheenDelay}ms` } as React.CSSProperties}
      initial={{ opacity: 0, scale: 0.985, x: 14 }}
      animate={inView ? { opacity: 1, scale: 1, x: 0 } : { opacity: 0, scale: 0.985, x: 14 }}
      transition={{ duration: 0.34, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}

interface AnimatedListProps {
  children: ReactNode;
  className?: string;
  resetKey?: string | number;
  staggerDelay?: number;
}

export default function AnimatedList({ children, className = "", resetKey, staggerDelay = 0.07 }: AnimatedListProps) {
  return (
    <div key={resetKey} className={["animated-list", className].filter(Boolean).join(" ")}>
      {Children.map(children, (child, index) => (
        <AnimatedItem delay={Math.min(index, 4) * staggerDelay} index={index}>
          {child}
        </AnimatedItem>
      ))}
    </div>
  );
}
