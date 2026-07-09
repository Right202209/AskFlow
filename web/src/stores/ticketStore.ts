import { create } from "zustand";
import type { Ticket } from "@/types/ticket";
import * as ticketService from "@/services/ticket";

interface TicketState {
  tickets: Ticket[];
  currentTicket: Ticket | null;
  isLoading: boolean;

  fetchTickets: (limit?: number, offset?: number) => Promise<void>;
  fetchTicket: (id: string) => Promise<void>;
  clearCurrent: () => void;
}

export const useTicketStore = create<TicketState>()((set) => ({
  tickets: [],
  currentTicket: null,
  isLoading: false,

  fetchTickets: async (limit = 20, offset = 0) => {
    set({ isLoading: true });
    try {
      const tickets = await ticketService.getTickets(limit, offset);
      set({ tickets });
    } finally {
      set({ isLoading: false });
    }
  },

  fetchTicket: async (id) => {
    set({ isLoading: true });
    try {
      const ticket = await ticketService.getTicket(id);
      set({ currentTicket: ticket });
    } finally {
      set({ isLoading: false });
    }
  },

  clearCurrent: () => set({ currentTicket: null }),
}));
