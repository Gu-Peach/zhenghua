import { create } from "zustand";
import type { AnswerBook } from "@/apis/answer-comparison";
import { useSessionStore } from "./session-store";

interface AnswerState {
  books: Record<string, AnswerBook>;
  opened: Record<string, boolean>;
  put: (project: string, book: AnswerBook) => void;
  remove: (project: string) => void;
  open: (project: string, value: boolean) => void;
}

// Deliberately no persist middleware: reference answers belong to this login in memory only.
export const useAnswerStore = create<AnswerState>(set => ({
  books: {}, opened: {},
  put: (project, book) => set(state => ({ books: { ...state.books, [project]: book } })),
  remove: project => set(state => { const books = { ...state.books }; delete books[project]; return { books }; }),
  open: (project, value) => set(state => ({ opened: { ...state.opened, [project]: value } })),
}));

useSessionStore.subscribe((state, previous) => {
  if (state.session?.user.id !== previous.session?.user.id) useAnswerStore.setState({ books: {}, opened: {} });
});
