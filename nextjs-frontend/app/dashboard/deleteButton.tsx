"use client";

import { useRouter } from "next/navigation";

import { backendFetch } from "@/lib/backend-fetch";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";

interface DeleteButtonProps {
  itemId: string;
}

export function DeleteButton({ itemId }: DeleteButtonProps) {
  const router = useRouter();

  const handleDelete = async () => {
    const response = await backendFetch(`/api/v1/items/${itemId}`, {
      method: "DELETE",
    });
    if (response.status === 401) {
      router.push("/login");
      return;
    }
    if (response.ok) {
      router.refresh();
    }
  };

  return (
    <DropdownMenuItem
      className="text-red-500 cursor-pointer"
      onClick={handleDelete}
    >
      Delete
    </DropdownMenuItem>
  );
}
