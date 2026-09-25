// src/types.ts
export interface MeResponse {
  id: number;
  username: string;
  email?: string;
  role?: string;
  // add any other fields returned by UserSerializer
}
